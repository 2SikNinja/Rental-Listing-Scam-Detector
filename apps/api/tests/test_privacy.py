"""Tests for app/security/privacy.py: redaction and keyed hashing."""

import pytest

from app.schemas.listing import ListingSubmission
from app.security.privacy import (
    emailPlaceholder,
    fingerprintDescription,
    hashContactValue,
    phonePlaceholder,
    prepareListingForStorage,
    redactContactInfo,
)

secretKey = "d" * 64
otherSecretKey = "e" * 64


# ---------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "phoneText",
    ["626-555-0101", "(626) 555-0101", "626.555.0101", "+1 626 555 0101", "6265550101"],
)
def testPhoneNumbersAreRemovedInAnyFormat(phoneText):
    redactedText, _, foundPhones = redactContactInfo(f"Call me at {phoneText} today.")
    assert "555" not in redactedText
    assert phonePlaceholder in redactedText
    assert foundPhones == ["6265550101"]


def testEmailsAreRemovedAndLowercased():
    redactedText, foundEmails, _ = redactContactInfo("Email Owner.Name@Example.com for details.")
    assert "example.com" not in redactedText.lower()
    assert emailPlaceholder in redactedText
    assert foundEmails == ["owner.name@example.com"]


def testOrdinaryNumbersAreNotTreatedAsPhones():
    """Prices, ZIP codes, and square footage must survive redaction."""
    text = "Rent is $2100 for 950 sq ft in 91101, deposit 1500."
    redactedText, _, foundPhones = redactContactInfo(text)
    assert redactedText == text
    assert foundPhones == []


# ---------------------------------------------------------------------
# Keyed hashing
# ---------------------------------------------------------------------
def testSameValueGivesSameHash():
    assert hashContactValue("phone", "6265550101", secretKey) == hashContactValue("phone", "6265550101", secretKey)


def testDifferentSecretGivesDifferentHash():
    """Without the secret, a stolen database can't be matched against guesses."""
    assert hashContactValue("phone", "6265550101", secretKey) != hashContactValue("phone", "6265550101", otherSecretKey)


def testKindIsPartOfTheHash():
    assert hashContactValue("email", "x", secretKey) != hashContactValue("name", "x", secretKey)


def testHashIs64HexCharacters():
    valueHmac = hashContactValue("phone", "6265550101", secretKey)
    assert len(valueHmac) == 64
    assert all(character in "0123456789abcdef" for character in valueHmac)


# ---------------------------------------------------------------------
# Full preparation for storage
# ---------------------------------------------------------------------
def testNoRawContactInfoSurvivesPreparation():
    submission = ListingSubmission(
        title="Call 626-555-0199 now",
        description="Nice place. Text 626-555-0101 or email owner@example.com to apply.",
        contact={"name": "Jane  Doe", "email": "Owner@Example.com", "phone": "(626) 555-0101"},
    )
    prepared = prepareListingForStorage(submission, secretKey)

    storedText = f"{prepared.titleRedacted} {prepared.descriptionRedacted}"
    for rawValue in ("626", "0101", "0199", "owner@", "Jane"):
        assert rawValue not in storedText


def testDuplicateContactsAreStoredOnce():
    """The same phone in the text and the contact field is one contact."""
    submission = ListingSubmission(
        description="Text 626-555-0101 to see the apartment this weekend.",
        contact={"phone": "626.555.0101", "email": "owner@example.com"},
    )
    prepared = prepareListingForStorage(submission, secretKey)
    kinds = sorted(contact.kind for contact in prepared.contacts)
    assert kinds == ["email", "phone"]


def testEmailDomainIsKeptForDomainChecks():
    submission = ListingSubmission(
        description="A normal apartment listing description here.",
        contact={"email": "someone@tempmail.example"},
    )
    emailContact = prepareListingForStorage(submission, secretKey).contacts[0]
    assert emailContact.emailDomain == "tempmail.example"


def testFingerprintIgnoresCaseAndSpacing():
    assert fingerprintDescription("Nice  2BR\napartment") == fingerprintDescription("nice 2br apartment")
