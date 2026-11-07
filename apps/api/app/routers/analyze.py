"""
Analysis endpoints.

  POST /analyze         JSON body, no photos (API clients, Chrome extension)
  POST /analyze/upload  multipart form: the listing as JSON plus photos (website)

Both share one pipeline (runAnalysis), so results are identical apart from
the photo check. The router only coordinates:
  1. run each available check  (app/checks/)
  2. score the signals         (app/scoring/engine.py + weights.yaml)
  3. save the result           (app/repositories/, best effort)
  4. build the response, including safety tips and skip reasons
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import logging
import time
from typing import Callable
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.exceptions import RequestValidationError
from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from app.checks.addressCheck import runAddressCheck
from app.checks.base import CheckOutcome
from app.checks.contactCheck import findDescriptionReuseSignals, runContactCheck
from app.checks.photoCheck import runPhotoCheck
from app.checks.priceCheck import runPriceCheck
from app.checks.textCheck import runTextCheck
from app.config import getSettings
from app.db import getConnectionPool
from app.dependencies import (
    getCrossListingFinder,
    getGeocoder,
    getPhoneLineTypeLookup,
    getPhotoMatcher,
    getSaleListingLookup,
)
from app.repositories.analysisRepository import saveAnalysis
from app.repositories.crossListingRepository import CrossListingFinder
from app.repositories.photoRepository import PhotoMatcher
from app.schemas.listing import AnalysisResult, CheckName, ListingSubmission, SignalOut
from app.scoring.engine import ScoringConfig, getScoringConfig, scoreOutcomes
from app.scoring.safetyTips import buildSafetyTips
from app.security.privacy import prepareListingForStorage
from app.security.rateLimit import enforceRateLimit
from app.security.uploadValidation import PhotoRejected, validatePhoto
from app.services.externalLookups import Geocoder, PhoneLineTypeLookup, SaleListingLookup
from app.services.marketRents import MarketRentProvider, getMarketRentProvider
from app.services.photoHashing import PhotoHashes, hashPhoto

router = APIRouter(tags=["analysis"])
logger = logging.getLogger(__name__)

allCheckNames: list[CheckName] = ["price", "text", "photo", "address", "contact"]

temporarilyUnavailableReason = "This check is temporarily unavailable. Please try again later."


@dataclass(frozen=True)
class AnalysisSources:
    """Every outside data source one analysis may use. Any of them can be None (not configured)."""

    marketRentProvider: MarketRentProvider
    scoringConfig: ScoringConfig
    connectionPool: ConnectionPool | None
    photoMatcher: PhotoMatcher | None
    crossListingFinder: CrossListingFinder | None
    geocoder: Geocoder | None
    saleListingLookup: SaleListingLookup | None
    phoneLineTypeLookup: PhoneLineTypeLookup | None


def getAnalysisSources(
    marketRentProvider: MarketRentProvider = Depends(getMarketRentProvider),
    scoringConfig: ScoringConfig = Depends(getScoringConfig),
    connectionPool: ConnectionPool | None = Depends(getConnectionPool),
    photoMatcher: PhotoMatcher | None = Depends(getPhotoMatcher),
    crossListingFinder: CrossListingFinder | None = Depends(getCrossListingFinder),
    geocoder: Geocoder | None = Depends(getGeocoder),
    saleListingLookup: SaleListingLookup | None = Depends(getSaleListingLookup),
    phoneLineTypeLookup: PhoneLineTypeLookup | None = Depends(getPhoneLineTypeLookup),
) -> AnalysisSources:
    return AnalysisSources(marketRentProvider, scoringConfig, connectionPool, photoMatcher,
                           crossListingFinder, geocoder, saleListingLookup, phoneLineTypeLookup)


def runSafely(checkName: CheckName, analysisId: uuid.UUID, checkFunction: Callable[[], CheckOutcome]) -> CheckOutcome:
    """An outage in one lookup costs that one check, never the whole analysis."""
    try:
        return checkFunction()
    except Exception:
        logger.exception("%s check failed for analysis %s", checkName, analysisId)
        return CheckOutcome(checkName=checkName, ran=False, skipReason=temporarilyUnavailableReason)


def runAnalysis(submission: ListingSubmission, photoHashes: list[PhotoHashes], sources: AnalysisSources) -> AnalysisResult:
    startTime = time.perf_counter()
    analysisId = uuid.uuid4()
    redactedListing = prepareListingForStorage(submission, getSettings().contactHashSecret.get_secret_value())
    contactHashes = frozenset(
        contact.valueHmac for contact in redactedListing.contacts if contact.kind in ("email", "phone")
    )
    lineTypesByHash: dict[str, str] = {}

    def contactCheck() -> CheckOutcome:
        outcome, foundLineTypes = runContactCheck(
            submission, redactedListing, sources.crossListingFinder, sources.phoneLineTypeLookup
        )
        lineTypesByHash.update(foundLineTypes)
        return outcome

    def textCheck() -> CheckOutcome:
        # Wording rules run in memory; copied-description matching needs the database
        wordingOutcome = runTextCheck(submission)
        try:
            reuseSignals = findDescriptionReuseSignals(submission, redactedListing, sources.crossListingFinder)
        except Exception:
            logger.exception("Description reuse lookup failed for analysis %s", analysisId)
            reuseSignals = []
        return CheckOutcome(checkName="text", ran=True, signals=[*wordingOutcome.signals, *reuseSignals])

    # The slow checks (database queries, outside APIs) run at the same time,
    # so total wait is the slowest one, not the sum of all of them.
    with ThreadPoolExecutor(max_workers=4) as checkExecutor:
        futureOutcomes = [
            checkExecutor.submit(runSafely, "text", analysisId, textCheck),
            checkExecutor.submit(runSafely, "photo", analysisId,
                                 lambda: runPhotoCheck(submission, photoHashes, contactHashes, sources.photoMatcher)),
            checkExecutor.submit(runSafely, "address", analysisId,
                                 lambda: runAddressCheck(submission, sources.geocoder, sources.saleListingLookup)),
            checkExecutor.submit(runSafely, "contact", analysisId, contactCheck),
        ]
        checkOutcomes: list[CheckOutcome] = [
            runPriceCheck(submission, sources.marketRentProvider),
            *(future.result() for future in futureOutcomes),
        ]
    scoringConfig = sources.scoringConfig
    scoreResult = scoreOutcomes(checkOutcomes, scoringConfig)

    # Saving is best effort: if the database is down, the user still gets
    # their result. The failure is logged (without any listing content).
    wasSaved = False
    if sources.connectionPool is not None:
        try:
            durationMs = round((time.perf_counter() - startTime) * 1000)
            with sources.connectionPool.connection() as connection:
                saveAnalysis(connection, analysisId, submission, redactedListing, scoreResult, durationMs,
                             photoHashes, lineTypesByHash)
            wasSaved = True
        except Exception:
            logger.exception("Could not save analysis %s", analysisId)

    checksRun: list[CheckName] = [outcome.checkName for outcome in checkOutcomes if outcome.ran]
    checksSkipped = [checkName for checkName in allCheckNames if checkName not in checksRun]

    skipReasons: dict[str, str] = {}
    for outcome in checkOutcomes:
        if not outcome.ran and outcome.skipReason:
            skipReasons[outcome.checkName] = outcome.skipReason

    return AnalysisResult(
        analysisId=analysisId,
        saved=wasSaved,
        riskLevel=scoreResult.riskLevel,
        totalPoints=scoreResult.totalPoints,
        riskThresholds={
            "medium": scoringConfig.riskThresholds.medium,
            "high": scoringConfig.riskThresholds.high,
        },
        scoringConfigVersion=scoreResult.configVersion,
        signals=[
            SignalOut(
                checkName=scored.signal.checkName,
                signalCode=scored.signal.signalCode,
                severity=scored.signal.severity,
                points=scored.points,
                explanation=scored.signal.explanation,
                evidence=scored.signal.evidence,
            )
            for scored in scoreResult.scoredSignals
        ],
        checksRun=checksRun,
        checksSkipped=checksSkipped,
        skipReasons=skipReasons,
        safetyTips=buildSafetyTips(scoreResult.scoredSignals),
    )


@router.post("/analyze", response_model=AnalysisResult, dependencies=[Depends(enforceRateLimit)])
def analyzeListing(
    submission: ListingSubmission,
    sources: AnalysisSources = Depends(getAnalysisSources),
) -> AnalysisResult:
    """
    Analyze a listing sent as JSON (no photos).

    FastAPI validates `submission` before this runs and injects the data
    sources, so tests can replace any of them with a small fake.
    """
    return runAnalysis(submission, [], sources)


def photoError(photoIndex: int, message: str) -> HTTPException:
    """Same error shape as FastAPI's own 422 responses, so the website handles both."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[{"loc": ["body", "photos", photoIndex], "msg": message, "type": "value_error"}],
    )


@router.post("/analyze/upload", response_model=AnalysisResult, dependencies=[Depends(enforceRateLimit)])
def analyzeListingWithPhotos(
    listing: str = Form(..., max_length=60_000, description="The listing, as the same JSON /analyze accepts"),
    photos: list[UploadFile] = File(default=[]),
    sources: AnalysisSources = Depends(getAnalysisSources),
) -> AnalysisResult:
    """
    Analyze a listing with photos (multipart form).

    Photos are validated, hashed in memory, and discarded. Only their
    hashes are ever stored.
    """
    settings = getSettings()

    try:
        submission = ListingSubmission.model_validate_json(listing)
    except ValidationError as validationError:
        # Report errors with the same field paths as the JSON endpoint
        raise RequestValidationError(
            [{**error, "loc": ("body", *error["loc"])} for error in validationError.errors(include_url=False)]
        ) from None

    if len(photos) > settings.maxPhotosPerListing:
        raise photoError(settings.maxPhotosPerListing, f"Upload at most {settings.maxPhotosPerListing} photos.")

    photoHashes: list[PhotoHashes] = []
    seenFiles: set[str] = set()
    totalBytes = 0
    for photoIndex, uploadedPhoto in enumerate(photos):
        try:
            validatedPhoto = validatePhoto(uploadedPhoto.file, settings.maxPhotoBytes)
        except PhotoRejected as rejection:
            # The file name is never echoed back: it's client-controlled text
            raise photoError(photoIndex, f"Photo {photoIndex + 1} {rejection}.") from None
        finally:
            uploadedPhoto.file.close()

        totalBytes += len(validatedPhoto.imageBytes)
        if totalBytes > settings.maxTotalPhotoBytes:
            raise photoError(photoIndex, f"Photos add up to more than {settings.maxTotalPhotoBytes // (1024 * 1024)} MB.")

        hashes = hashPhoto(validatedPhoto)
        if hashes.contentSha256 not in seenFiles:  # the same file attached twice counts once
            seenFiles.add(hashes.contentSha256)
            photoHashes.append(hashes)

    return runAnalysis(submission, photoHashes, sources)
