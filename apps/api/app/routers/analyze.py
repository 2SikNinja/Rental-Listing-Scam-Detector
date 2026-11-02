"""
POST /analyze: the endpoint the paste form and Chrome extension call.

Step 2 version: validates the listing and returns a correctly shaped
result. No detection checks exist yet, so every check is reported as
skipped. Steps 3 and 4 plug the price and text checks and the scoring
engine in here without changing the request or response format.
"""

import uuid

from fastapi import APIRouter

from app.schemas.listing import AnalysisResult, CheckName, ListingSubmission

router = APIRouter(tags=["analysis"])

allCheckNames: list[CheckName] = ["price", "text", "photo", "address", "contact"]

# Shown on every result, whatever the score. A low score is never proof
# that a listing is safe, so these always appear.
generalSafetyTips = [
    "Never send a deposit or rent before you have seen the unit in person or by live video.",
    "Be wary of payment by wire transfer, gift cards, Zelle, or crypto. These are hard to reverse.",
    "Search the address online to check whether it is listed for sale or by another landlord.",
    "Ask for a signed lease and check that the landlord's name matches public property records.",
    "Keep all communication on the original listing platform when possible.",
]


@router.post("/analyze", response_model=AnalysisResult)
def analyzeListing(submission: ListingSubmission) -> AnalysisResult:
    """
    Analyze a pasted rental listing and return a risk assessment.

    FastAPI has already validated `submission` against ListingSubmission
    before this function runs. Invalid input never reaches this code; the
    client gets a 422 response that names the bad field instead.
    """
    checksRun: list[CheckName] = []
    checksSkipped = [checkName for checkName in allCheckNames if checkName not in checksRun]

    return AnalysisResult(
        analysisId=uuid.uuid4(),
        riskLevel="low",
        totalPoints=0,
        signals=[],
        checksRun=checksRun,
        checksSkipped=checksSkipped,
        safetyTips=generalSafetyTips,
    )
