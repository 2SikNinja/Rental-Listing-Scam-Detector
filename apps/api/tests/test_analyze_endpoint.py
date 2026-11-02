"""
Tests for the HTTP layer: /health and POST /analyze.

TestClient sends real HTTP requests to the app in memory, without
starting uvicorn, so these run fast and need no network.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

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
