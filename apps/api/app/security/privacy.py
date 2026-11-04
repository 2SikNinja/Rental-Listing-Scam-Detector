"""
Privacy helpers: what gets stored, and in what form.

Rules (matching the database schema):
  - Emails and phone numbers are removed from the stored description.
  - Contact details are stored only as keyed HMAC-SHA256 hashes. The same
    phone number always produces the same hash, so we can still detect
    "this number appeared on 6 other listings", but the number itself is
    never stored.
  - A plain SHA-256 of a phone number would NOT be safe: there are only
    about 10 billion US numbers, so an attacker with the database could
    hash them all and reverse it. The secret key (CONTACT_HASH_SECRET)
    lives outside the database, which makes that attack impossible.
"""

from dataclasses import dataclass
import hashlib
import hmac
import re

from app.checks.textCheck import normalizeText
from app.schemas.listing import ListingSubmission

emailInTextPattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# US-style numbers with optional +1 and common separators:
# 626-555-0101, (626) 555-0101, 626.555.0101, +1 626 555 0101
phoneInTextPattern = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")

emailPlaceholder = "[email removed]"
phonePlaceholder = "[phone removed]"


@dataclass(frozen=True)
class HashedContact:
    kind: str                  # "email", "phone", or "name"
    valueHmac: str             # 64 hex characters
    emailDomain: str | None    # kept for the throwaway-domain check, not identifying on its own


@dataclass(frozen=True)
class RedactedListing:
    titleRedacted: str | None
    descriptionRedacted: str
    descriptionFingerprint: str
    contacts: list[HashedContact]


def normalizePhoneDigits(rawPhone: str) -> str:
    digitsOnly = re.sub(r"\D", "", rawPhone)
    if len(digitsOnly) == 11 and digitsOnly.startswith("1"):
        digitsOnly = digitsOnly[1:]
    return digitsOnly


def hashContactValue(kind: str, normalizedValue: str, secretKey: str) -> str:
    """Keyed hash. The kind is included so an email and a name never collide."""
    message = f"{kind}:{normalizedValue}".encode("utf-8")
    return hmac.new(secretKey.encode("utf-8"), message, hashlib.sha256).hexdigest()


def redactContactInfo(text: str) -> tuple[str, list[str], list[str]]:
    """Remove emails and phone numbers. Returns (redacted text, emails, phones)."""
    foundEmails = [match.lower() for match in emailInTextPattern.findall(text)]
    withoutEmails = emailInTextPattern.sub(emailPlaceholder, text)
    foundPhones = [normalizePhoneDigits(match) for match in phoneInTextPattern.findall(withoutEmails)]
    withoutPhones = phoneInTextPattern.sub(phonePlaceholder, withoutEmails)
    return withoutPhones, foundEmails, foundPhones


def fingerprintDescription(redactedDescription: str) -> str:
    """
    SHA-256 of the normalized, redacted text. Identical descriptions get
    identical fingerprints even if spacing or capitalization differ, so
    exact copies can be found with one indexed lookup.
    """
    return hashlib.sha256(normalizeText(redactedDescription).encode("utf-8")).hexdigest()


def prepareListingForStorage(submission: ListingSubmission, secretKey: str) -> RedactedListing:
    redactedDescription, emailsInText, phonesInText = redactContactInfo(submission.description)
    redactedTitle, emailsInTitle, phonesInTitle = redactContactInfo(submission.title or "")
    emailsInText = emailsInText + emailsInTitle
    phonesInText = phonesInText + phonesInTitle

    allEmails = list(emailsInText)
    if submission.contact.email:
        allEmails.append(submission.contact.email)
    allPhones = list(phonesInText)
    if submission.contact.phone:
        allPhones.append(submission.contact.phone)

    contacts: list[HashedContact] = []
    seenHashes: set[str] = set()

    def addContact(kind: str, normalizedValue: str, emailDomain: str | None = None) -> None:
        valueHmac = hashContactValue(kind, normalizedValue, secretKey)
        if valueHmac not in seenHashes:
            seenHashes.add(valueHmac)
            contacts.append(HashedContact(kind, valueHmac, emailDomain))

    for email in allEmails:
        addContact("email", email, email.rsplit("@", 1)[-1])
    for phone in allPhones:
        if 10 <= len(phone) <= 15:
            addContact("phone", phone)
    if submission.contact.name:
        addContact("name", re.sub(r"\s+", " ", submission.contact.name.strip().lower()))

    return RedactedListing(
        titleRedacted=redactedTitle or None,
        descriptionRedacted=redactedDescription,
        descriptionFingerprint=fingerprintDescription(redactedDescription),
        contacts=contacts,
    )
