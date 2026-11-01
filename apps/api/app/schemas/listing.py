"""
Request and response models for the /analyze endpoint.

This is the API contract between the Next.js form (and later the Chrome
extension) and the backend. Every field is validated and cleaned here,
before any detection check runs, so the checks can trust their inputs.

Field names are camelCase so the JSON the frontend sends and receives
matches these Python names exactly, with no alias mapping needed.
"""

from decimal import Decimal
import re
from typing import Literal
from urllib.parse import urlparse
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------
CheckName = Literal["price", "text", "photo", "address", "contact"]
Severity = Literal["info", "low", "medium", "high"]
RiskLevel = Literal["low", "medium", "high"]
ListingSource = Literal["paste", "extension"]

# Control characters (except tab and newline) can hide text, break logs,
# or smuggle content past filters, so they are stripped from all text.
controlCharPattern = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
zipCodePattern = re.compile(r"^[0-9]{5}$")
stateCodePattern = re.compile(r"^[A-Z]{2}$")
emailPattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def cleanText(rawValue: str | None) -> str | None:
    """Remove control characters and trim. Empty strings become None."""
    if rawValue is None:
        return None
    cleanedValue = controlCharPattern.sub("", rawValue).strip()
    return cleanedValue or None


class StrictModel(BaseModel):
    """
    Base for all request models.

    extra="forbid" rejects unknown fields instead of silently ignoring
    them. This blocks mass-assignment style attacks, where a client tries
    to set fields it shouldn't control (like a risk score).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------
class AddressInput(StrictModel):
    street: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    stateCode: str | None = Field(default=None, max_length=2)
    zipCode: str | None = Field(default=None, max_length=5)

    @field_validator("street", "city")
    @classmethod
    def cleanAddressText(cls, rawValue: str | None) -> str | None:
        return cleanText(rawValue)

    @field_validator("stateCode")
    @classmethod
    def validateStateCode(cls, rawValue: str | None) -> str | None:
        cleanedValue = cleanText(rawValue)
        if cleanedValue is None:
            return None
        upperValue = cleanedValue.upper()
        if not stateCodePattern.match(upperValue):
            raise ValueError("stateCode must be a 2-letter state abbreviation, like CA")
        return upperValue

    @field_validator("zipCode")
    @classmethod
    def validateZipCode(cls, rawValue: str | None) -> str | None:
        cleanedValue = cleanText(rawValue)
        if cleanedValue is None:
            return None
        if not zipCodePattern.match(cleanedValue):
            raise ValueError("zipCode must be exactly 5 digits")
        return cleanedValue


class ContactInput(StrictModel):
    name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("name")
    @classmethod
    def cleanName(cls, rawValue: str | None) -> str | None:
        return cleanText(rawValue)

    @field_validator("email")
    @classmethod
    def validateEmail(cls, rawValue: str | None) -> str | None:
        cleanedValue = cleanText(rawValue)
        if cleanedValue is None:
            return None
        lowerValue = cleanedValue.lower()
        if not emailPattern.match(lowerValue):
            raise ValueError("email does not look like a valid address")
        return lowerValue

    @field_validator("phone")
    @classmethod
    def normalizePhone(cls, rawValue: str | None) -> str | None:
        """
        Normalize to digits only, so "(626) 555-0101" and "626.555.0101"
        hash to the same value later for duplicate-contact detection.
        A leading 1 (US country code) is dropped from 11-digit numbers.
        """
        cleanedValue = cleanText(rawValue)
        if cleanedValue is None:
            return None
        digitsOnly = re.sub(r"\D", "", cleanedValue)
        if len(digitsOnly) == 11 and digitsOnly.startswith("1"):
            digitsOnly = digitsOnly[1:]
        if not 10 <= len(digitsOnly) <= 15:
            raise ValueError("phone must contain 10 to 15 digits")
        return digitsOnly


class ListingSubmission(StrictModel):
    """What the user pastes into the form."""

    source: ListingSource = "paste"
    title: str | None = Field(default=None, max_length=300)
    description: str = Field(min_length=20, max_length=20000)
    monthlyRent: Decimal | None = Field(default=None, gt=0, le=100000, decimal_places=2)
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    bathrooms: Decimal | None = Field(default=None, ge=0, le=20, decimal_places=1)
    address: AddressInput = Field(default_factory=AddressInput)
    contact: ContactInput = Field(default_factory=ContactInput)
    sourceUrl: str | None = Field(default=None, max_length=2048)

    @field_validator("title")
    @classmethod
    def cleanTitle(cls, rawValue: str | None) -> str | None:
        return cleanText(rawValue)

    @field_validator("description")
    @classmethod
    def cleanDescription(cls, rawValue: str) -> str:
        cleanedValue = cleanText(rawValue) or ""
        if len(cleanedValue) < 20:
            raise ValueError("description must be at least 20 characters after cleanup")
        return cleanedValue

    @field_validator("sourceUrl")
    @classmethod
    def validateSourceUrl(cls, rawValue: str | None) -> str | None:
        cleanedValue = cleanText(rawValue)
        if cleanedValue is None:
            return None
        parsedUrl = urlparse(cleanedValue)
        if parsedUrl.scheme not in ("http", "https") or not parsedUrl.hostname:
            raise ValueError("sourceUrl must be an http or https link")
        return cleanedValue

    @property
    def sourceDomain(self) -> str | None:
        """Only the domain is stored, never the full URL (privacy)."""
        if self.sourceUrl is None:
            return None
        hostName = urlparse(self.sourceUrl).hostname or ""
        return hostName.removeprefix("www.") or None

    @property
    def monthlyRentCents(self) -> int | None:
        """Money is stored as integer cents to avoid float rounding errors."""
        if self.monthlyRent is None:
            return None
        return int(self.monthlyRent * 100)


# ---------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------
class SignalOut(BaseModel):
    """One red flag (or informational note) and why it was raised."""

    checkName: CheckName
    signalCode: str
    severity: Severity
    points: int
    explanation: str
    evidence: dict = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    """What the results page displays."""

    analysisId: uuid.UUID
    riskLevel: RiskLevel
    totalPoints: int
    signals: list[SignalOut]
    checksRun: list[CheckName]
    checksSkipped: list[CheckName]
    safetyTips: list[str]
    disclaimer: str = (
        "This is an automated risk assessment, not a verdict. A high score means the "
        "listing shares patterns with known scams. A low score does not guarantee the "
        "listing is legitimate. Always verify before sending money."
    )
