"""
POST /analyze: the endpoint the paste form and Chrome extension call.

The router only coordinates: it runs each available check, turns the
signals into points, and builds the response. The detection logic lives
in app/checks/, one module per check.

Step 3 status: the text and price checks run. The points and risk thresholds below
are a temporary stand-in. Step 4 replaces them with the scoring engine
(app/scoring/engine.py) and tunable weights in weights.yaml, including
an "insufficient data" result when too few checks could run.
"""

import uuid

from fastapi import APIRouter, Depends

from app.checks.base import CheckOutcome
from app.checks.priceCheck import runPriceCheck
from app.checks.textCheck import runTextCheck
from app.services.marketRents import MarketRentProvider, getMarketRentProvider
from app.schemas.listing import (
    AnalysisResult,
    CheckName,
    ListingSubmission,
    RiskLevel,
    Severity,
    SignalOut,
)

router = APIRouter(tags=["analysis"])

allCheckNames: list[CheckName] = ["price", "text", "photo", "address", "contact"]

# Temporary scoring (moves to weights.yaml in Step 4)
interimSeverityPoints: dict[Severity, int] = {"info": 0, "low": 5, "medium": 15, "high": 30}
interimHighThreshold = 50
interimMediumThreshold = 20

# Shown on every result, whatever the score. A low score is never proof
# that a listing is safe, so these always appear.
generalSafetyTips = [
    "Never send a deposit or rent before you have seen the unit in person or by live video.",
    "Be wary of payment by wire transfer, gift cards, Zelle, or crypto. These are hard to reverse.",
    "Search the address online to check whether it is listed for sale or by another landlord.",
    "Ask for a signed lease and check that the landlord's name matches public property records.",
    "Keep all communication on the original listing platform when possible.",
]


def interimRiskLevel(totalPoints: int) -> RiskLevel:
    if totalPoints >= interimHighThreshold:
        return "high"
    if totalPoints >= interimMediumThreshold:
        return "medium"
    return "low"


@router.post("/analyze", response_model=AnalysisResult)
def analyzeListing(
    submission: ListingSubmission,
    marketRentProvider: MarketRentProvider = Depends(getMarketRentProvider),
) -> AnalysisResult:
    """
    Analyze a pasted rental listing and return a risk assessment.

    FastAPI has already validated `submission` against ListingSubmission
    before this function runs. Invalid input never reaches this code; the
    client gets a 422 response that names the bad field instead.

    `marketRentProvider` is supplied by FastAPI's dependency injection, so
    tests can swap in a small fake data set.
    """
    checkOutcomes: list[CheckOutcome] = [
        runPriceCheck(submission, marketRentProvider),
        runTextCheck(submission),
    ]

    signalsOut: list[SignalOut] = []
    for outcome in checkOutcomes:
        for detectedSignal in outcome.signals:
            signalsOut.append(
                SignalOut(
                    checkName=detectedSignal.checkName,
                    signalCode=detectedSignal.signalCode,
                    severity=detectedSignal.severity,
                    points=interimSeverityPoints[detectedSignal.severity],
                    explanation=detectedSignal.explanation,
                    evidence=detectedSignal.evidence,
                )
            )

    # Most serious flags first, so the results page leads with them
    signalsOut.sort(key=lambda signalOut: signalOut.points, reverse=True)
    totalPoints = sum(signalOut.points for signalOut in signalsOut)

    checksRun: list[CheckName] = [outcome.checkName for outcome in checkOutcomes if outcome.ran]
    checksSkipped = [checkName for checkName in allCheckNames if checkName not in checksRun]
    skipReasons = {
        outcome.checkName: outcome.skipReason
        for outcome in checkOutcomes
        if not outcome.ran and outcome.skipReason
    }

    return AnalysisResult(
        analysisId=uuid.uuid4(),
        riskLevel=interimRiskLevel(totalPoints),
        totalPoints=totalPoints,
        signals=signalsOut,
        checksRun=checksRun,
        checksSkipped=checksSkipped,
        skipReasons=skipReasons,
        safetyTips=generalSafetyTips,
    )
