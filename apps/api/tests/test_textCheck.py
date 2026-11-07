"""
Tests for app/checks/textCheck.py.

Each rule gets at least one "should flag" case. The legitimate listings
and negation cases matter just as much: false positives would unfairly
flag honest landlords.
"""

import pytest

from app.checks.textCheck import normalizeText, runTextCheck
from app.schemas.listing import ListingSubmission


def flaggedCodes(description: str, title: str | None = None) -> set[str]:
    submission = ListingSubmission(description=description, title=title)
    outcome = runTextCheck(submission)
    return {signal.signalCode for signal in outcome.signals}


# ---------------------------------------------------------------------
# One positive case per rule (several phrasings where useful)
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("description", "expectedCode"),
    [
        ("I am currently overseas for work but the place is ready.", "OWNER_UNAVAILABLE"),
        ("We relocated for a new job and need a tenant fast.", "OWNER_UNAVAILABLE"),
        ("My husband is deployed so we are renting the house out.", "OWNER_UNAVAILABLE"),
        ("Sorry, I can't show the unit right now because of renovations.", "CANNOT_SHOW_UNIT"),
        ("No viewings available, please drive by to see the outside.", "CANNOT_SHOW_UNIT"),
        ("Please do not disturb the current tenants during your visit.", "CANNOT_SHOW_UNIT"),
        ("Once approved, the keys will be mailed to you within two days.", "KEYS_MAILED"),
        ("After payment I will ship you the keys by FedEx overnight.", "KEYS_MAILED"),
        ("A deposit is required before viewing the apartment in person.", "PAYMENT_BEFORE_VIEWING"),
        ("Send the first month payment today to hold the unit for you.", "PAYMENT_BEFORE_VIEWING"),
        ("A $200 holding fee secures this apartment for one week.", "PAYMENT_BEFORE_VIEWING"),
        ("Payment by wire transfer only, details sent after approval.", "UNTRACEABLE_PAYMENT"),
        ("Application fee can be paid with Apple or Steam gift cards.", "UNTRACEABLE_PAYMENT"),
        ("We accept Bitcoin and USDT for the security deposit.", "UNTRACEABLE_PAYMENT"),
        ("Rent can be sent through Zelle at the start of each month.", "PEER_TO_PEER_PAYMENT"),
        ("Contact me on WhatsApp for faster replies about the place.", "OFF_PLATFORM_CONTACT"),
        ("Please email me directly instead of replying on this site.", "OFF_PLATFORM_CONTACT"),
        ("Include your social security number in your first message.", "PERSONAL_INFO_REQUEST"),
        ("This deal won't last, first come first served on the unit.", "URGENCY_PRESSURE"),
    ],
)
def testRuleFlagsScamWording(description, expectedCode):
    assert expectedCode in flaggedCodes(description)


def testTitleIsScannedToo():
    assert "KEYS_MAILED" in flaggedCodes(
        title="Keys will be mailed, cheap 2BR",
        description="Nice apartment with updated kitchen and parking.",
    )


# ---------------------------------------------------------------------
# Legitimate listings should not be flagged
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "legitimateDescription",
    [
        "Bright 2 bedroom apartment with in-unit laundry. Open house Saturday 10am to noon. "
        "Apply online through our leasing portal after your tour.",
        "Managed by a local property company. Tours available daily. Rent is paid through our secure "
        "resident portal. Pets welcome with deposit.",
        "Quiet one bedroom near the library. Call the leasing office to schedule a showing.",
    ],
)
def testLegitimateListingsHaveNoFlags(legitimateDescription):
    assert flaggedCodes(legitimateDescription) == set()


# ---------------------------------------------------------------------
# Negation: honest landlords often warn about scams in their listings
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "warningText",
    [
        "We never accept wire transfers or gift cards for any payment.",
        "No Zelle, Venmo, or Cash App. Checks only at the leasing office.",
        "We will not mail keys. Pick them up in person at move-in.",
        "There is no holding fee, and you can tour before applying.",
    ],
)
def testNegatedWarningsAreNotFlagged(warningText):
    assert flaggedCodes(warningText) == set()


def testNegationDoesNotCrossSentences():
    """'No pets.' should not cancel a payment request in the next sentence."""
    assert "UNTRACEABLE_PAYMENT" in flaggedCodes("Lovely house with a yard. No pets. Wire transfer only for deposit.")


def testNegationDoesNotApplyToCannotShow():
    """'No viewings' is the red flag itself, so negation must not cancel it."""
    assert "CANNOT_SHOW_UNIT" in flaggedCodes("No showings at this time due to current occupants.")


# ---------------------------------------------------------------------
# Output shape and evidence
# ---------------------------------------------------------------------
def testFullScamListingRaisesMultipleSignals():
    codes = flaggedCodes("Owner is overseas, keys will be mailed after you send the deposit by Zelle.")
    assert {"OWNER_UNAVAILABLE", "KEYS_MAILED", "PEER_TO_PEER_PAYMENT"} <= codes


def testEachRuleAppearsOnceWithEvidence():
    submission = ListingSubmission(description="Pay with Zelle. Zelle only. Send Zelle today, Venmo also fine.")
    outcome = runTextCheck(submission)
    peerSignals = [signal for signal in outcome.signals if signal.signalCode == "PEER_TO_PEER_PAYMENT"]
    assert len(peerSignals) == 1
    matchedPhrases = peerSignals[0].evidence["matchedPhrases"]
    assert 1 <= len(matchedPhrases) <= 3
    assert "zelle" in matchedPhrases


def testCheckAlwaysReportsThatItRan():
    outcome = runTextCheck(ListingSubmission(description="A plain listing with nothing unusual in it at all."))
    assert outcome.ran is True
    assert outcome.checkName == "text"


def testNormalizeTextHandlesCurlyQuotesAndSpacing():
    assert normalizeText("Can’t   SHOW\nthe unit") == "can't show the unit"


def testCurlyApostropheStillMatches():
    assert "CANNOT_SHOW_UNIT" in flaggedCodes("Sorry, I can’t show the apartment until next month.")


# ---------------------------------------------------------------------
# Rules added after the Step 8 evaluation (dev split findings)
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("description", "expectedCode"),
    [
        ("The keys and the signed contract will be shipped overnight once paid.", "KEYS_MAILED"),
        ("My spouse and I are missionaries serving abroad this year.", "OWNER_UNAVAILABLE"),
        ("I work in Texas now so I cannot come by to show it.", "OWNER_UNAVAILABLE"),
        ("Sorry, I can't meet you in person, I travel constantly.", "OWNER_UNAVAILABLE"),
        ("A $400 deposit is needed to hold it for you until Friday.", "PAYMENT_BEFORE_VIEWING"),
        ("Send half the deposit to take the unit off the market.", "PAYMENT_BEFORE_VIEWING"),
        ("We list it publicly and it will remain on the market until the deposit funds clear.", "PAYMENT_BEFORE_VIEWING"),
        ("Please wire the first month directly to my account.", "UNTRACEABLE_PAYMENT"),
        ("We accept wire transfers for the security deposit.", "UNTRACEABLE_PAYMENT"),
        ("Fees are paid through an international money transfer company.", "UNTRACEABLE_PAYMENT"),
        ("You can send the deposit with Chime or Apple Pay.", "PEER_TO_PEER_PAYMENT"),
        ("For pictures and the address, message me on Instagram.", "OFF_PLATFORM_CONTACT"),
        ("I take care of everything over text, no need to call.", "OFF_PLATFORM_CONTACT"),
    ],
)
def testRulesAddedFromEvaluation(description, expectedCode):
    assert expectedCode in flaggedCodes(description)


@pytest.mark.parametrize(
    "warningText",
    [
        "We will never ask for wire transfers, gift cards, Bitcoin or Zelle.",
        "Do not send Venmo, Cash App or Apple Pay payments to anyone claiming to be us.",
    ],
)
def testNegatedListsAreNotFlagged(warningText):
    assert flaggedCodes(warningText) == set()


def testNegatedListDoesNotHideAFollowingRequest():
    """The warning is ignored, but a separate payment request in the next sentence still counts."""
    codes = flaggedCodes("We never accept gift cards or crypto. Send the deposit through Zelle today.")
    assert "PEER_TO_PEER_PAYMENT" in codes
    assert "UNTRACEABLE_PAYMENT" not in codes


def testHoldingDepositAfterApprovalIsAKnownFalsePositive():
    """
    Documented limitation from the evaluation (legit-12): a legitimate
    holding deposit after approval still matches. Kept as a test so any
    future fix is noticed and the README limitation can be updated.
    """
    assert "PAYMENT_BEFORE_VIEWING" in flaggedCodes(
        "After your application is approved, a holding deposit secures the unit."
    )
