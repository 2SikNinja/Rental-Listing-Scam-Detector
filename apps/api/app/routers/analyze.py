"""
POST /analyze: the endpoint the paste form and Chrome extension call.

The router only coordinates:
  1. run each available check  (app/checks/)
  2. score the signals         (app/scoring/engine.py + weights.yaml)
  3. build the response, including safety tips and skip reasons
"""

import uuid

from fastapi import APIRouter, Depends

from app.checks.base import CheckOutcome
from app.checks.priceCheck import runPriceCheck
from app.checks.textCheck import runTextCheck
from app.schemas.listing import AnalysisResult, CheckName, ListingSubmission, SignalOut
from app.scoring.engine import ScoringConfig, getScoringConfig, scoreOutcomes
from app.scoring.safetyTips import buildSafetyTips
from app.services.marketRents import MarketRentProvider, getMarketRentProvider

router = APIRouter(tags=["analysis"])

allCheckNames: list[CheckName] = ["price", "text", "photo", "address", "contact"]

# Checks that are planned but not built yet, so skipped results say why
notYetAvailableReason = "This check is not available yet."


@router.post("/analyze", response_model=AnalysisResult)
def analyzeListing(
    submission: ListingSubmission,
    marketRentProvider: MarketRentProvider = Depends(getMarketRentProvider),
    scoringConfig: ScoringConfig = Depends(getScoringConfig),
) -> AnalysisResult:
    """
    Analyze a pasted rental listing and return a risk assessment.

    FastAPI has already validated `submission` before this runs, and it
    injects the market data and scoring config, so tests can replace
    either one with a small fake.
    """
    checkOutcomes: list[CheckOutcome] = [
        runPriceCheck(submission, marketRentProvider),
        runTextCheck(submission),
    ]

    scoreResult = scoreOutcomes(checkOutcomes, scoringConfig)

    checksRun: list[CheckName] = [outcome.checkName for outcome in checkOutcomes if outcome.ran]
    checksSkipped = [checkName for checkName in allCheckNames if checkName not in checksRun]

    skipReasons: dict[str, str] = {}
    for outcome in checkOutcomes:
        if not outcome.ran and outcome.skipReason:
            skipReasons[outcome.checkName] = outcome.skipReason
    for checkName in checksSkipped:
        skipReasons.setdefault(checkName, notYetAvailableReason)

    return AnalysisResult(
        analysisId=uuid.uuid4(),
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
