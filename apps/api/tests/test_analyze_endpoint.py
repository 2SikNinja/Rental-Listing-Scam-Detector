"""
Tests for the HTTP layer: /health and POST /analyze.

TestClient sends real HTTP requests to the app in memory, without
starting uvicorn, so these run fast and need no network.

Every test here uses fake market rent data (typical 2BR in 91101 is
$2,000), so results never depend on the real HUD file on disk.
"""

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.dependencies import getGeocoder, getPhoneLineTypeLookup, getSaleListingLookup
from app.scoring.engine import getScoringConfig
from app.security.rateLimit import SlidingWindowRateLimiter, getRateLimiter
from app.services.marketRents import getMarketRentProvider
from tests.fakes import FakeMarketRentProvider
from tests.test_scoring import testConfig

client = TestClient(app)


@pytest.fixture(autouse=True)
def useFakeDependencies():
    """Fixed market data and scoring weights, so tuning weights.yaml never breaks these tests."""
    app.dependency_overrides[getMarketRentProvider] = lambda: FakeMarketRentProvider(zipCode="91101")
    app.dependency_overrides[getScoringConfig] = lambda: testConfig
    # Rate limiting has its own tests; here it would throttle the many requests
    app.dependency_overrides[getRateLimiter] = lambda: SlidingWindowRateLimiter(maxRequests=10_000)
    for externalDependency in (getGeocoder, getSaleListingLookup, getPhoneLineTypeLookup):
        app.dependency_overrides[externalDependency] = lambda: None  # never call real outside services
    yield
    app.dependency_overrides.clear()

validListing = {
    "title": "2BR apartment",
    "description": "Spacious 2 bedroom apartment near the park, available now.",
    "monthlyRent": "2100",
    "bedrooms": 2,
    "address": {"city": "Pasadena", "stateCode": "CA", "zipCode": "91101"},
    "contact": {"email": "owner@example.com"},
}


def testHealthReturnsOk():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def testAnalyzeAcceptsValidListing():
    response = client.post("/analyze", json=validListing)
    assert response.status_code == 200
    body = response.json()
    assert body["riskLevel"] in ("low", "medium", "high")
    assert "analysisId" in body
    assert body["disclaimer"]
    assert len(body["safetyTips"]) > 0


def testAnalyzeReportsSkippedChecks():
    """Until checks exist, every check must be listed as skipped, not silently missing."""
    body = client.post("/analyze", json=validListing).json()
    assert set(body["checksRun"]) | set(body["checksSkipped"]) == {
        "price", "text", "photo", "address", "contact",
    }


def testObviousScamListingIsHighRisk():
    scamListing = {
        **validListing,
        "description": "Owner is overseas, keys will be mailed after you send the deposit by wire transfer.",
    }
    body = client.post("/analyze", json=scamListing).json()
    assert body["riskLevel"] == "high"
    assert "text" in body["checksRun"]
    signalCodes = {signal["signalCode"] for signal in body["signals"]}
    assert {"OWNER_UNAVAILABLE", "KEYS_MAILED", "UNTRACEABLE_PAYMENT"} <= signalCodes
    # Most serious signals are listed first
    signalPoints = [signal["points"] for signal in body["signals"]]
    assert signalPoints == sorted(signalPoints, reverse=True)


def testCleanListingHasNoSignals():
    body = client.post("/analyze", json=validListing).json()
    assert body["signals"] == []
    assert body["riskLevel"] == "low"
    assert {"price", "text"} <= set(body["checksRun"])


def testPriceCheckFlagsCheapListing():
    cheapListing = {**validListing, "monthlyRent": "800"}  # fake typical 2BR is $2,000
    body = client.post("/analyze", json=cheapListing).json()
    assert "price" in body["checksRun"]
    priceSignals = [signal for signal in body["signals"] if signal["checkName"] == "price"]
    assert priceSignals[0]["signalCode"] == "RENT_FAR_BELOW_MARKET"


def testSkippedPriceCheckExplainsWhy():
    listingWithoutRent = {key: value for key, value in validListing.items() if key != "monthlyRent"}
    body = client.post("/analyze", json=listingWithoutRent).json()
    assert "price" in body["checksSkipped"]
    assert "monthly rent" in body["skipReasons"]["price"]


def testMissingPriceDataGivesInsufficientDataNotLow():
    # Only the text check can run: no rent (price), no contacts, no street, no photos
    listingWithoutRent = {key: value for key, value in validListing.items() if key not in ("monthlyRent", "contact")}
    body = client.post("/analyze", json=listingWithoutRent).json()
    assert body["riskLevel"] == "insufficient_data"


def testEverySkippedCheckSaysWhy():
    """'Couldn't check' must never look like 'nothing found'."""
    body = client.post("/analyze", json=validListing).json()
    assert body["checksSkipped"], "this listing has no photos or street, so some checks must skip"
    for checkName in body["checksSkipped"]:
        assert body["skipReasons"][checkName]


def testResponseIncludesScoringVersionAndThresholds():
    body = client.post("/analyze", json=validListing).json()
    assert body["scoringConfigVersion"] == "test-1"
    assert body["riskThresholds"] == {"medium": 20, "high": 50}


def testSafetyTipsMatchTheSignalsFound():
    scamListing = {**validListing, "description": "Great place. The keys will be mailed to you after approval."}
    body = client.post("/analyze", json=scamListing).json()
    assert "keys" in body["safetyTips"][0].lower()


def testAnalyzeRejectsInvalidListingWith422():
    badListing = {**validListing, "address": {"zipCode": "123"}}
    response = client.post("/analyze", json=badListing)
    assert response.status_code == 422
    errorFields = [".".join(map(str, error["loc"])) for error in response.json()["detail"]]
    assert any("zipCode" in fieldPath for fieldPath in errorFields)


def testAnalyzeRejectsUnknownField():
    response = client.post("/analyze", json={**validListing, "totalPoints": 0})
    assert response.status_code == 422


def testAnalyzeRejectsMissingBody():
    response = client.post("/analyze")
    assert response.status_code == 422


def testCorsAllowsConfiguredOrigin():
    response = client.options(
        "/analyze",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def testCorsBlocksUnknownOrigin():
    response = client.options(
        "/analyze",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


# ---------------------------------------------------------------------
# POST /analyze/upload (multipart: listing JSON + photos)
# ---------------------------------------------------------------------
import json  # noqa: E402

from tests.imageFactory import sceneBytes  # noqa: E402


def uploadListing(listing: dict, photoFiles: list[tuple[str, bytes, str]]):
    return client.post(
        "/analyze/upload",
        data={"listing": json.dumps(listing)},
        files=[("photos", photoFile) for photoFile in photoFiles],
    )


def testUploadWithPhotosWorksWithoutDatabase():
    response = uploadListing(validListing, [("room.jpg", sceneBytes(1), "image/jpeg")])
    assert response.status_code == 200
    body = response.json()
    assert "database" in body["skipReasons"]["photo"]  # no DB in unit tests, so the check says why


def testUploadWithoutPhotosMatchesJsonEndpoint():
    uploadBody = uploadListing(validListing, []).json()
    jsonBody = client.post("/analyze", json=validListing).json()
    assert uploadBody["riskLevel"] == jsonBody["riskLevel"]
    assert uploadBody["skipReasons"]["photo"] == "No photos were uploaded."


def testUploadRejectsNonImageWithFieldError():
    response = uploadListing(validListing, [("notes.jpg", b"this is not an image at all" * 5, "image/jpeg")])
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "photos", 0]
    assert "notes.jpg" not in error["msg"]  # client-supplied file names are never echoed


def testUploadRejectsTooManyPhotos():
    tooMany = [(f"p{index}.jpg", sceneBytes(index), "image/jpeg") for index in range(11)]
    response = uploadListing(validListing, tooMany)
    assert response.status_code == 422
    assert "at most" in response.json()["detail"][0]["msg"]


def testUploadReportsListingErrorsWithSameFieldPaths():
    response = uploadListing({**validListing, "address": {"zipCode": "123"}}, [])
    assert response.status_code == 422
    errorPaths = [".".join(map(str, error["loc"])) for error in response.json()["detail"]]
    assert "body.address.zipCode" in errorPaths


def testUploadRejectsMalformedListingJson():
    response = client.post("/analyze/upload", data={"listing": "{not json"})
    assert response.status_code == 422


def testOutsideServiceOutageOnlySkipsThatCheck():
    """If the geocoder is down, the address check says so and everything else still runs."""
    from app.services.externalLookups import ExternalLookupError

    class BrokenGeocoder:
        def geocode(self, street, city, stateCode, zipCode):
            raise ExternalLookupError("Census geocoder request failed")

    app.dependency_overrides[getGeocoder] = lambda: BrokenGeocoder()
    listingWithStreet = {**validListing, "address": {**validListing["address"], "street": "123 Main St"}}
    response = client.post("/analyze", json=listingWithStreet)
    assert response.status_code == 200
    body = response.json()
    assert "temporarily unavailable" in body["skipReasons"]["address"]
    assert {"price", "text", "contact"} <= set(body["checksRun"])
