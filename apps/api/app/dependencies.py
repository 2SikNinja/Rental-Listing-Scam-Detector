"""
FastAPI dependency providers for every outside data source.

Each returns either a working client or None when that feature isn't
configured (no database, no API key). The checks treat None as "skip
with a reason", so the app degrades gracefully instead of failing.

Tests replace any of these with fakes through app.dependency_overrides,
so no test ever touches the network or a real database by accident.
"""

from functools import lru_cache

from fastapi import Depends
import httpx
from psycopg_pool import ConnectionPool

from app.config import getSettings
from app.db import getConnectionPool
from app.repositories.crossListingRepository import CrossListingFinder, PostgresCrossListingFinder
from app.repositories.photoRepository import PhotoMatcher, PostgresPhotoMatcher
from app.services.externalLookups import (
    CensusGeocoder,
    Geocoder,
    PhoneLineTypeLookup,
    RentcastSaleListings,
    SaleListingLookup,
    TwilioLineTypeLookup,
)


@lru_cache
def getHttpClient() -> httpx.Client:
    """One shared client reuses connections (and TLS sessions) across requests."""
    return httpx.Client(
        timeout=httpx.Timeout(getSettings().externalRequestTimeoutSeconds),
        headers={"User-Agent": "rental-scam-detector/1.0"},
        follow_redirects=False,
    )


def getGeocoder() -> Geocoder | None:
    if getSettings().geocodingProvider == "none":
        return None
    return CensusGeocoder(getHttpClient())


def getSaleListingLookup() -> SaleListingLookup | None:
    apiKey = getSettings().rentcastApiKey
    return RentcastSaleListings(getHttpClient(), apiKey.get_secret_value()) if apiKey else None


def getPhoneLineTypeLookup() -> PhoneLineTypeLookup | None:
    settings = getSettings()
    if not settings.twilioEnabled:
        return None
    return TwilioLineTypeLookup(getHttpClient(), settings.twilioAccountSid, settings.twilioAuthToken.get_secret_value())


def getPhotoMatcher(connectionPool: ConnectionPool | None = Depends(getConnectionPool)) -> PhotoMatcher | None:
    return PostgresPhotoMatcher(connectionPool) if connectionPool is not None else None


def getCrossListingFinder(
    connectionPool: ConnectionPool | None = Depends(getConnectionPool),
) -> CrossListingFinder | None:
    return PostgresCrossListingFinder(connectionPool) if connectionPool is not None else None
