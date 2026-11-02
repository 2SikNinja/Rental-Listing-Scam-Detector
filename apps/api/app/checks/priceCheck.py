"""
Price check: compares the asking rent to typical rent for the same ZIP
code and bedroom count.

Why it matters: an unrealistically low price is the bait in most rental
scams, and unlike wording, scammers can't easily hide it. A low price
is the whole point of the lure.

Thresholds (moving to weights.yaml with the scoring engine in Step 4):
  - 50% or less of market rent  -> high severity
  - 70% or less of market rent  -> medium severity
  - otherwise                   -> no signal

These are deliberately conservative. HUD's figure is near the 40th
percentile, so plenty of honest listings sit somewhat below it. Only
large gaps are flagged.
"""

from app.checks.base import CheckOutcome, DetectedSignal
from app.schemas.listing import ListingSubmission
from app.services.marketRents import MarketRentProvider, maxHudBedrooms

highSeverityRatio = 0.50
mediumSeverityRatio = 0.70


def formatDollars(amountCents: int) -> str:
    return f"${amountCents / 100:,.0f}"


def describeBedrooms(bedrooms: int) -> str:
    return "studio" if bedrooms == 0 else f"{bedrooms}-bedroom"


def runPriceCheck(submission: ListingSubmission, marketRentProvider: MarketRentProvider) -> CheckOutcome:
    # A check that can't run says so, instead of quietly reporting "no problems"
    if submission.monthlyRentCents is None:
        return CheckOutcome(checkName="price", ran=False, skipReason="No monthly rent was entered.")
    if submission.bedrooms is None:
        return CheckOutcome(checkName="price", ran=False, skipReason="No bedroom count was entered.")
    if submission.address.zipCode is None:
        return CheckOutcome(checkName="price", ran=False, skipReason="No ZIP code was entered.")
    if not marketRentProvider.isLoaded:
        return CheckOutcome(checkName="price", ran=False, skipReason="Market rent data is not loaded on the server.")

    zipCode = submission.address.zipCode
    marketRent = marketRentProvider.getMarketRent(zipCode, submission.bedrooms)
    if marketRent is None:
        return CheckOutcome(
            checkName="price",
            ran=False,
            skipReason=f"No market rent data is available for ZIP code {zipCode}.",
        )

    askingCents = submission.monthlyRentCents
    rentRatio = askingCents / marketRent.monthlyRentCents
    percentBelow = round((1 - rentRatio) * 100)

    if rentRatio > mediumSeverityRatio:
        return CheckOutcome(checkName="price", ran=True)

    severity = "high" if rentRatio <= highSeverityRatio else "medium"
    signalCode = "RENT_FAR_BELOW_MARKET" if severity == "high" else "RENT_BELOW_MARKET"

    bedroomNote = ""
    if submission.bedrooms > maxHudBedrooms:
        bedroomNote = f" (compared with the {maxHudBedrooms}-bedroom figure, the largest size HUD publishes)"

    explanation = (
        f"The asking rent of {formatDollars(askingCents)} is about {percentBelow}% below the typical "
        f"{formatDollars(marketRent.monthlyRentCents)} for a {describeBedrooms(submission.bedrooms)} unit "
        f"in ZIP code {zipCode}{bedroomNote}. Prices far below market are a common lure in rental scams."
    )

    return CheckOutcome(
        checkName="price",
        ran=True,
        signals=[
            DetectedSignal(
                checkName="price",
                signalCode=signalCode,
                severity=severity,
                explanation=explanation,
                evidence={
                    "askingRentCents": askingCents,
                    "marketRentCents": marketRent.monthlyRentCents,
                    "percentBelowMarket": percentBelow,
                    "comparedBedrooms": min(submission.bedrooms, maxHudBedrooms),
                    "fiscalYear": marketRent.fiscalYear,
                    "dataSource": marketRent.dataSource,
                },
            )
        ],
    )
