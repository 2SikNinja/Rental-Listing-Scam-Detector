"""
Tests for app/security/rateLimit.py.

A fake clock replaces real time, so "wait 60 seconds" is instant.
"""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request

from app.security.rateLimit import SlidingWindowRateLimiter, enforceRateLimit, getClientIp, getRateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fakeClock():
    return FakeClock()


# ---------------------------------------------------------------------
# Sliding window logic
# ---------------------------------------------------------------------
def testAllowsUpToTheLimitThenBlocks(fakeClock):
    rateLimiter = SlidingWindowRateLimiter(maxRequests=3, windowSeconds=60, clock=fakeClock)
    assert [rateLimiter.checkRequest("1.1.1.1") for _ in range(3)] == [None, None, None]
    assert rateLimiter.checkRequest("1.1.1.1") is not None


def testRetryAfterCountsDownToOldestRequestExpiring(fakeClock):
    rateLimiter = SlidingWindowRateLimiter(maxRequests=1, windowSeconds=60, clock=fakeClock)
    rateLimiter.checkRequest("1.1.1.1")
    fakeClock.advance(20)
    assert rateLimiter.checkRequest("1.1.1.1") == pytest.approx(40)


def testWindowSlidesSoOldRequestsStopCounting(fakeClock):
    rateLimiter = SlidingWindowRateLimiter(maxRequests=2, windowSeconds=60, clock=fakeClock)
    rateLimiter.checkRequest("1.1.1.1")
    fakeClock.advance(30)
    rateLimiter.checkRequest("1.1.1.1")
    assert rateLimiter.checkRequest("1.1.1.1") is not None   # 2 in the last 60s
    fakeClock.advance(31)                                      # first request now expired
    assert rateLimiter.checkRequest("1.1.1.1") is None


def testBlockedRequestsDoNotExtendTheBlock(fakeClock):
    """Hammering while blocked must not keep you blocked forever."""
    rateLimiter = SlidingWindowRateLimiter(maxRequests=1, windowSeconds=60, clock=fakeClock)
    rateLimiter.checkRequest("1.1.1.1")
    for _ in range(50):
        rateLimiter.checkRequest("1.1.1.1")
    fakeClock.advance(61)
    assert rateLimiter.checkRequest("1.1.1.1") is None


def testEachClientHasItsOwnLimit(fakeClock):
    rateLimiter = SlidingWindowRateLimiter(maxRequests=1, windowSeconds=60, clock=fakeClock)
    assert rateLimiter.checkRequest("1.1.1.1") is None
    assert rateLimiter.checkRequest("2.2.2.2") is None


def testIdleClientsAreCleanedUp(fakeClock):
    rateLimiter = SlidingWindowRateLimiter(maxRequests=5, windowSeconds=60, clock=fakeClock)
    rateLimiter.checkRequest("1.1.1.1")
    fakeClock.advance(120)
    rateLimiter.removeIdleClients(fakeClock() - 60)
    assert "1.1.1.1" not in rateLimiter.requestTimesByClient


# ---------------------------------------------------------------------
# Client IP detection
# ---------------------------------------------------------------------
def buildRequest(forwardedFor: str | None = None, clientHost: str = "10.0.0.1") -> Request:
    headers = [(b"x-forwarded-for", forwardedFor.encode())] if forwardedFor else []
    return Request({"type": "http", "headers": headers, "client": (clientHost, 1234)})


def testIgnoresForwardedHeaderWhenNotBehindProxy():
    """Locally, a client could fake X-Forwarded-For to dodge the limit."""
    assert getClientIp(buildRequest("9.9.9.9"), trustProxyHeaders=False) == "10.0.0.1"


def testUsesLastForwardedIpBehindProxy():
    """Earlier entries can be typed by the client; the last is added by the proxy."""
    assert getClientIp(buildRequest("6.6.6.6, 203.0.113.7"), trustProxyHeaders=True) == "203.0.113.7"


def testFallsBackToConnectionIpWithoutHeader():
    assert getClientIp(buildRequest(), trustProxyHeaders=True) == "10.0.0.1"


# ---------------------------------------------------------------------
# HTTP behavior
# ---------------------------------------------------------------------
def testEndpointReturns429WithRetryAfterHeader(fakeClock):
    miniApp = FastAPI()

    @miniApp.get("/limited", dependencies=[Depends(enforceRateLimit)])
    def limitedEndpoint() -> dict[str, str]:
        return {"status": "ok"}

    # One shared limiter, like the cached one the real app uses
    sharedLimiter = SlidingWindowRateLimiter(2, 60, clock=fakeClock)
    miniApp.dependency_overrides[getRateLimiter] = lambda: sharedLimiter

    miniClient = TestClient(miniApp)
    assert miniClient.get("/limited").status_code == 200
    assert miniClient.get("/limited").status_code == 200
    blockedResponse = miniClient.get("/limited")
    assert blockedResponse.status_code == 429
    assert blockedResponse.headers["retry-after"] == "60"
