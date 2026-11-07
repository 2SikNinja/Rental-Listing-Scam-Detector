"""
Integration tests against a real Postgres database.

These run the real migrations and connect as the least-privilege
scam_api role, exactly like production. They are skipped unless
TEST_API_DATABASE_URL is set (CI sets it up with a Postgres container).

Locally:
    TEST_ADMIN_DATABASE_URL=postgresql://owner:pw@localhost:5432/scamtest
    TEST_API_DATABASE_URL=postgresql://scam_api:pw@localhost:5432/scamtest
"""

import os
import uuid

from fastapi.testclient import TestClient
import psycopg
from psycopg_pool import ConnectionPool
import pytest

from app.db import getConnectionPool
from app.main import app
from app.scoring.engine import getScoringConfig
from app.security.rateLimit import SlidingWindowRateLimiter, getRateLimiter
from app.services.marketRents import getMarketRentProvider
from tests.fakes import FakeMarketRentProvider
from tests.test_scoring import testConfig

apiDatabaseUrl = os.environ.get("TEST_API_DATABASE_URL")
adminDatabaseUrl = os.environ.get("TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(not apiDatabaseUrl, reason="TEST_API_DATABASE_URL not set")

client = TestClient(app)

scamListing = {
    "title": "2BR apartment, call 626-555-0101",
    "description": "Owner is overseas, keys will be mailed. Email owner@example.com or text 626-555-0101.",
    "monthlyRent": "800",
    "bedrooms": 2,
    "address": {"city": "Pasadena", "stateCode": "CA", "zipCode": "91101"},
    "contact": {"name": "Pat Smith", "email": "owner@example.com", "phone": "626-555-0101"},
}


@pytest.fixture(scope="module")
def apiPool():
    pool = ConnectionPool(apiDatabaseUrl, min_size=1, max_size=2, open=True,
                          kwargs={"prepare_threshold": None})
    yield pool
    pool.close()


@pytest.fixture(autouse=True)
def useTestDependencies(apiPool):
    app.dependency_overrides[getConnectionPool] = lambda: apiPool
    app.dependency_overrides[getMarketRentProvider] = lambda: FakeMarketRentProvider(zipCode="91101")
    app.dependency_overrides[getScoringConfig] = lambda: testConfig
    app.dependency_overrides[getRateLimiter] = lambda: SlidingWindowRateLimiter(maxRequests=10_000)
    yield
    app.dependency_overrides.clear()


def fetchAll(query: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(apiDatabaseUrl) as connection:
        return connection.execute(query, params).fetchall()


def testAnalysisIsSavedWithAllParts():
    body = client.post("/analyze", json=scamListing).json()
    assert body["saved"] is True
    analysisId = uuid.UUID(body["analysisId"])

    analysisRows = fetchAll(
        "select risk_level::text, total_points, status::text, scoring_config_version, listing_id "
        "from public.analyses where id = %s", (analysisId,))
    assert len(analysisRows) == 1
    riskLevel, totalPoints, status, configVersion, listingId = analysisRows[0]
    assert (riskLevel, totalPoints, status, configVersion) == (body["riskLevel"], body["totalPoints"], "complete", "test-1")

    savedSignalCodes = {row[0] for row in fetchAll(
        "select signal_code from public.signals where analysis_id = %s", (analysisId,))}
    assert savedSignalCodes == {signal["signalCode"] for signal in body["signals"]}

    contactKinds = sorted(row[0] for row in fetchAll(
        "select kind::text from public.listing_contacts where listing_id = %s", (listingId,)))
    assert contactKinds == ["email", "name", "phone"]


def testNoRawContactInfoIsStored():
    analysisId = client.post("/analyze", json=scamListing).json()["analysisId"]
    title, description = fetchAll(
        "select l.title, l.description_redacted from public.listings l "
        "join public.analyses a on a.listing_id = l.id where a.id = %s", (analysisId,))[0]
    storedText = f"{title} {description}"
    assert "555-0101" not in storedText
    assert "owner@example.com" not in storedText
    assert "[phone removed]" in storedText


def testSameContactProducesSameHashAcrossListings():
    """This is what will power 'this phone number appeared on N other listings'."""
    firstId = client.post("/analyze", json=scamListing).json()["analysisId"]
    secondId = client.post("/analyze", json=scamListing).json()["analysisId"]
    query = (
        "select c.value_hmac from public.listing_contacts c "
        "join public.analyses a on a.listing_id = c.listing_id "
        "where a.id = %s and c.kind = 'phone'"
    )
    assert fetchAll(query, (firstId,)) == fetchAll(query, (secondId,))


def testApiRoleCannotDeleteOrChangeData():
    with psycopg.connect(apiDatabaseUrl, autocommit=True) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("delete from public.listings")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("update public.analyses set risk_level = 'low'")


def testDatabaseFailureStillReturnsResult():
    """If saving fails, the user still gets their analysis, with saved=false."""
    brokenPool = ConnectionPool("postgresql://nobody:wrong@127.0.0.1:1/none", min_size=0, max_size=1,
                                timeout=1, open=True)
    app.dependency_overrides[getConnectionPool] = lambda: brokenPool
    try:
        response = client.post("/analyze", json=scamListing)
    finally:
        brokenPool.close()
    assert response.status_code == 200
    assert response.json()["saved"] is False


# ---------------------------------------------------------------------
# Photo reuse across listings (real bit_count matching in Postgres)
# ---------------------------------------------------------------------
import json  # noqa: E402

from tests.imageFactory import imageToBytes, makeScene  # noqa: E402

uniqueSeed = uuid.uuid4().int % 1_000_000  # fresh "room" each test run, so old rows don't interfere


def uploadWithPhoto(listing: dict, photoBytes: bytes):
    return client.post("/analyze/upload", data={"listing": json.dumps(listing)},
                       files=[("photos", ("room.jpg", photoBytes, "image/jpeg"))]).json()


def testReusedPhotoUnderDifferentZipIsFlagged():
    roomPhoto = makeScene(uniqueSeed)
    firstListing = {**scamListing, "address": {"zipCode": "91101"}}
    firstBody = uploadWithPhoto(firstListing, imageToBytes(roomPhoto, "JPEG", quality=95))
    assert firstBody["saved"] is True
    assert "photo" in firstBody["checksRun"]
    assert not any(signal["checkName"] == "photo" for signal in firstBody["signals"])

    # Same room, re-saved smaller (different bytes), posted in another ZIP with another phone
    copiedListing = {**scamListing, "title": "Updated 2BR", "address": {"zipCode": "94063"},
                     "contact": {"phone": "415-555-0199"}, "description": "Lovely apartment, recently updated."}
    secondBody = uploadWithPhoto(copiedListing, imageToBytes(roomPhoto.resize((400, 300)), "JPEG", quality=60))
    photoSignals = [signal for signal in secondBody["signals"] if signal["checkName"] == "photo"]
    assert photoSignals[0]["signalCode"] == "PHOTO_REUSED_ELSEWHERE"
    assert set(photoSignals[0]["evidence"]["differences"]) == {"a different ZIP code", "different contact details"}


def testPhotoHashesAreStoredButNotImages():
    body = uploadWithPhoto(scamListing, imageToBytes(makeScene(uniqueSeed + 1), "JPEG"))
    storedRows = fetchAll(
        "select length(p.phash), length(p.dhash), p.width_px from public.listing_photos p "
        "join public.analyses a on a.listing_id = p.listing_id where a.id = %s", (body["analysisId"],))
    assert storedRows == [(64, 64, 800)]
