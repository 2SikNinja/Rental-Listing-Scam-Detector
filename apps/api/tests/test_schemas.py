"""Tests for app/schemas/listing.py: validation and cleanup of pasted listings."""

import pytest
from pydantic import ValidationError

from app.schemas.listing import ListingSubmission

validDescription = "Spacious 2 bedroom apartment near the park, available now."


def buildSubmission(**overrides) -> ListingSubmission:
    baseValues = {"description": validDescription}
    baseValues.update(overrides)
    return ListingSubmission.model_validate(baseValues)


# ---------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------
def testMinimalListingIsValid():
    submission = buildSubmission()
    assert submission.source == "paste"
    assert submission.monthlyRent is None
    assert submission.address.zipCode is None


def testRentIsConvertedToCents():
    submission = buildSubmission(monthlyRent="1200.50")
    assert submission.monthlyRentCents == 120050


def testStateCodeIsUppercased():
    submission = buildSubmission(address={"stateCode": "ca"})
    assert submission.address.stateCode == "CA"


def testEmailIsLowercased():
    submission = buildSubmission(contact={"email": "Owner@Example.COM"})
    assert submission.contact.email == "owner@example.com"


# ---------------------------------------------------------------------
# Phone normalization (needed so duplicate contacts match later)
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "phoneInput",
    ["(626) 555-0101", "626.555.0101", "626-555-0101", "+1 626 555 0101", "16265550101"],
)
def testPhoneFormatsNormalizeToSameDigits(phoneInput):
    submission = buildSubmission(contact={"phone": phoneInput})
    assert submission.contact.phone == "6265550101"


def testTooShortPhoneIsRejected():
    with pytest.raises(ValidationError, match="phone"):
        buildSubmission(contact={"phone": "555-0101"})


# ---------------------------------------------------------------------
# Input cleanup and rejection
# ---------------------------------------------------------------------
def testControlCharactersAreStripped():
    submission = buildSubmission(title="Nice\x00 apart\x07ment")
    assert submission.title == "Nice apartment"


def testBlankOptionalTextBecomesNone():
    submission = buildSubmission(title="   ")
    assert submission.title is None


def testShortDescriptionIsRejected():
    with pytest.raises(ValidationError):
        buildSubmission(description="too short")


def testDescriptionMadeOfControlCharactersIsRejected():
    with pytest.raises(ValidationError):
        buildSubmission(description="\x00" * 30)


@pytest.mark.parametrize("badZip", ["9175", "917540", "abcde", "91 754"])
def testBadZipIsRejected(badZip):
    with pytest.raises(ValidationError, match="zipCode"):
        buildSubmission(address={"zipCode": badZip})


def testBadStateCodeIsRejected():
    with pytest.raises(ValidationError, match="stateCode"):
        buildSubmission(address={"stateCode": "C1"})


def testBadEmailIsRejected():
    with pytest.raises(ValidationError, match="email"):
        buildSubmission(contact={"email": "not-an-email"})


@pytest.mark.parametrize("badRent", ["0", "-500", "100001"])
def testOutOfRangeRentIsRejected(badRent):
    with pytest.raises(ValidationError):
        buildSubmission(monthlyRent=badRent)


# ---------------------------------------------------------------------
# Security: unknown fields and unsafe URLs
# ---------------------------------------------------------------------
def testUnknownTopLevelFieldIsRejected():
    """Blocks mass assignment, like a client trying to set its own score."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        buildSubmission(riskLevel="low")


def testUnknownNestedFieldIsRejected():
    with pytest.raises(ValidationError, match="Extra inputs"):
        buildSubmission(contact={"email": "a@b.com", "isVerified": True})


@pytest.mark.parametrize(
    "badUrl",
    ["javascript:alert(1)", "file:///etc/passwd", "ftp://example.com/x", "not a url"],
)
def testNonHttpUrlsAreRejected(badUrl):
    with pytest.raises(ValidationError, match="sourceUrl"):
        buildSubmission(sourceUrl=badUrl)


def testSourceDomainKeepsOnlyTheHost():
    """Privacy: only the domain is kept, never the path or query string."""
    submission = buildSubmission(sourceUrl="https://www.example.org/listing/123?ref=abc")
    assert submission.sourceDomain == "example.org"
