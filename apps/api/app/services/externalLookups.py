"""
Clients for outside services used by the address and contact checks.

  CensusGeocoder        U.S. Census Bureau geocoder. Free, no API key.
  RentcastSaleListings  RentCast sale listings (optional, needs RENTCAST_API_KEY).
  TwilioLineTypeLookup  Twilio Lookup line type (optional, needs Twilio keys).

Design rules for every outside call:
  - Short timeouts, so a slow service can't hang the whole analysis.
  - Errors raise ExternalLookupError. The calling check turns that into
    "skipped: temporarily unavailable" instead of a wrong answer.
  - Each client sits behind a small interface (Protocol), so tests use
    fakes and never touch the network.
  - Only the minimum is sent out: the address to the geocoder, and the
    phone number to Twilio (only when that feature is turned on).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Protocol
from urllib.parse import quote

import httpx

censusGeocoderUrl = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
rentcastSaleListingsUrl = "https://api.rentcast.io/v1/listings/sale"
twilioLookupUrl = "https://lookups.twilio.com/v2/PhoneNumbers/{phoneE164}"

# Unit numbers often make the Census geocoder miss an otherwise valid street address
unitDesignatorPattern = re.compile(r"\s*,?\s*(?:apt|apartment|unit|suite|ste|#)\s*[\w-]+\s*$", re.IGNORECASE)


class ExternalLookupError(Exception):
    """An outside service failed or returned something unexpected."""


# ---------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class GeocodeResult:
    found: bool
    matchedAddress: str | None = None
    zipCode: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class Geocoder(Protocol):
    def geocode(self, street: str, city: str | None, stateCode: str | None, zipCode: str | None) -> GeocodeResult:
        ...


def removeUnitDesignator(street: str) -> str:
    return unitDesignatorPattern.sub("", street).strip()


class CensusGeocoder:
    def __init__(self, httpClient: httpx.Client):
        self.httpClient = httpClient

    def geocode(self, street: str, city: str | None, stateCode: str | None, zipCode: str | None) -> GeocodeResult:
        oneLineAddress = ", ".join(
            part for part in (removeUnitDesignator(street), city, stateCode, zipCode) if part
        )
        try:
            response = self.httpClient.get(
                censusGeocoderUrl,
                params={"address": oneLineAddress, "benchmark": "Public_AR_Current", "format": "json"},
            )
            response.raise_for_status()
            addressMatches = response.json()["result"]["addressMatches"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as lookupError:
            raise ExternalLookupError("Census geocoder request failed") from lookupError

        if not addressMatches:
            return GeocodeResult(found=False)
        bestMatch = addressMatches[0]
        return GeocodeResult(
            found=True,
            matchedAddress=bestMatch.get("matchedAddress"),
            zipCode=(bestMatch.get("addressComponents") or {}).get("zip"),
            latitude=(bestMatch.get("coordinates") or {}).get("y"),
            longitude=(bestMatch.get("coordinates") or {}).get("x"),
        )


# ---------------------------------------------------------------------
# For-sale listings
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class SaleListingStatus:
    found: bool
    isActive: bool = False
    lastSeenDate: datetime | None = None   # most recent listed/removed/updated date
    listPrice: int | None = None


class SaleListingLookup(Protocol):
    def lookup(self, fullAddress: str) -> SaleListingStatus:
        ...


def parseIsoDate(rawValue: object) -> datetime | None:
    if not isinstance(rawValue, str):
        return None
    try:
        parsedDate = datetime.fromisoformat(rawValue.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsedDate if parsedDate.tzinfo else parsedDate.replace(tzinfo=timezone.utc)


class RentcastSaleListings:
    def __init__(self, httpClient: httpx.Client, apiKey: str):
        self.httpClient = httpClient
        self.apiKey = apiKey

    def lookup(self, fullAddress: str) -> SaleListingStatus:
        try:
            response = self.httpClient.get(
                rentcastSaleListingsUrl,
                params={"address": fullAddress, "limit": 5},
                headers={"X-Api-Key": self.apiKey, "Accept": "application/json"},
            )
            if response.status_code == 404:
                return SaleListingStatus(found=False)
            response.raise_for_status()
            responseBody = response.json()
        except (httpx.HTTPError, ValueError) as lookupError:
            raise ExternalLookupError("RentCast request failed") from lookupError

        saleListings = responseBody if isinstance(responseBody, list) else [responseBody]
        saleListings = [listing for listing in saleListings if isinstance(listing, dict) and listing]
        if not saleListings:
            return SaleListingStatus(found=False)

        isActive = any(str(listing.get("status", "")).lower() == "active" for listing in saleListings)
        seenDates = [
            parsedDate
            for listing in saleListings
            for fieldName in ("lastSeenDate", "removedDate", "listedDate")
            if (parsedDate := parseIsoDate(listing.get(fieldName))) is not None
        ]
        listPrice = next((listing.get("price") for listing in saleListings if isinstance(listing.get("price"), int)), None)
        return SaleListingStatus(found=True, isActive=isActive,
                                 lastSeenDate=max(seenDates) if seenDates else None, listPrice=listPrice)


# ---------------------------------------------------------------------
# Phone line type
# ---------------------------------------------------------------------
class PhoneLineTypeLookup(Protocol):
    def lookupLineType(self, phoneDigits: str) -> str:
        """Returns 'mobile', 'landline', 'voip', or 'unknown' (the values the database allows)."""
        ...


twilioTypeToLineType = {"mobile": "mobile", "landline": "landline", "fixedVoip": "voip", "nonFixedVoip": "voip"}


class TwilioLineTypeLookup:
    def __init__(self, httpClient: httpx.Client, accountSid: str, authToken: str):
        self.httpClient = httpClient
        self.accountSid = accountSid
        self.authToken = authToken

    def lookupLineType(self, phoneDigits: str) -> str:
        phoneE164 = f"+1{phoneDigits}" if len(phoneDigits) == 10 else f"+{phoneDigits}"
        try:
            response = self.httpClient.get(
                twilioLookupUrl.format(phoneE164=quote(phoneE164, safe="")),  # "+" must be sent as %2B
                params={"Fields": "line_type_intelligence"},
                auth=(self.accountSid, self.authToken),
            )
            response.raise_for_status()
            lineTypeInfo = response.json().get("line_type_intelligence") or {}
        except (httpx.HTTPError, ValueError, AttributeError) as lookupError:
            raise ExternalLookupError("Twilio lookup failed") from lookupError
        return twilioTypeToLineType.get(lineTypeInfo.get("type"), "unknown")
