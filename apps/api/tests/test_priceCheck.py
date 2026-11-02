"""
Tests for app/checks/priceCheck.py.

A small fake provider stands in for HUD data, so these tests don't
depend on the real CSV and the numbers are easy to reason about:
typical 2BR rent in 90001 is exactly $2,000.
"""

import pytest

from app.checks.priceCheck import runPriceCheck
from app.schemas.listing import ListingSubmission
from tests.fakes import FakeMarketRentProvider

description = "Apartment available now near shops, parks, and public transit."


def priceOutcome(monthlyRent: str | None = "2000", bedrooms: int | None = 2, zipCode: str | None = "90001",
                 provider: FakeMarketRentProvider | None = None):
    submission = ListingSubmission(
        description=description,
        monthlyRent=monthlyRent,
        bedrooms=bedrooms,
        address={"zipCode": zipCode},
    )
    return runPriceCheck(submission, provider or FakeMarketRentProvider())


# ---------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("monthlyRent", "expectedCode", "expectedSeverity"),
    [
        ("2000", None, None),                                # at market
        ("1500", None, None),                                # 25% below: still normal
        ("1401", None, None),                                # just above the 70% line
        ("1400", "RENT_BELOW_MARKET", "medium"),             # exactly 70%
        ("1001", "RENT_BELOW_MARKET", "medium"),
        ("1000", "RENT_FAR_BELOW_MARKET", "high"),           # exactly 50%
        ("400", "RENT_FAR_BELOW_MARKET", "high"),
    ],
)
def testThresholds(monthlyRent, expectedCode, expectedSeverity):
    outcome = priceOutcome(monthlyRent=monthlyRent)
    assert outcome.ran is True
    if expectedCode is None:
        assert outcome.signals == []
    else:
        assert len(outcome.signals) == 1
        assert outcome.signals[0].signalCode == expectedCode
        assert outcome.signals[0].severity == expectedSeverity


def testHighRentIsNotFlagged():
    """This check only looks for suspiciously cheap listings."""
    assert priceOutcome(monthlyRent="9000").signals == []


# ---------------------------------------------------------------------
# Explanation and evidence
# ---------------------------------------------------------------------
def testExplanationStatesTheNumbers():
    signal = priceOutcome(monthlyRent="900").signals[0]
    assert "$900" in signal.explanation
    assert "$2,000" in signal.explanation
    assert "55%" in signal.explanation
    assert "90001" in signal.explanation
    assert signal.evidence["percentBelowMarket"] == 55
    assert signal.evidence["fiscalYear"] == 2027


def testStudioIsDescribedAsStudio():
    signal = priceOutcome(monthlyRent="500", bedrooms=0).signals[0]
    assert "studio" in signal.explanation


def testLargeHomesUseFourBedroomFigure():
    signal = priceOutcome(monthlyRent="1200", bedrooms=6).signals[0]
    assert signal.evidence["comparedBedrooms"] == 4
    assert "4-bedroom figure" in signal.explanation


# ---------------------------------------------------------------------
# Skipping: "couldn't check" must never look like "no problems found"
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("overrides", "reasonFragment"),
    [
        ({"monthlyRent": None}, "monthly rent"),
        ({"bedrooms": None}, "bedroom"),
        ({"zipCode": None}, "ZIP"),
        ({"zipCode": "99999"}, "99999"),
    ],
)
def testSkipsWithReasonWhenDataIsMissing(overrides, reasonFragment):
    outcome = priceOutcome(**overrides)
    assert outcome.ran is False
    assert outcome.signals == []
    assert reasonFragment in outcome.skipReason


def testSkipsWhenNoMarketDataLoaded():
    outcome = priceOutcome(provider=FakeMarketRentProvider(rentsByBedrooms={}))
    assert outcome.ran is False
    assert "not loaded" in outcome.skipReason
