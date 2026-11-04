"""
Per-IP rate limiting for the public API.

Algorithm: sliding window. For each client IP we keep the timestamps of
its recent requests. A new request is allowed only if fewer than
`maxRequests` happened in the last `windowSeconds`.

Why it matters: /analyze does real work on every call, and once the API
is public anyone can script thousands of requests. Rate limiting keeps
one client from running up costs or slowing the service for everyone.

Known limitation: counts live in memory, so each Cloud Run instance
keeps its own counts and they reset on restart. For a portfolio-scale
API that is acceptable. A shared store such as Redis, or Cloud Armor in
front of the service, would make the limit global.
"""

from collections import deque
from functools import lru_cache
import math
from threading import Lock
import time
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from app.config import getSettings

# Sweep out idle IPs every so often so memory can't grow forever
cleanupEveryRequests = 1000


class SlidingWindowRateLimiter:
    def __init__(self, maxRequests: int, windowSeconds: float = 60.0,
                 clock: Callable[[], float] = time.monotonic):
        self.maxRequests = maxRequests
        self.windowSeconds = windowSeconds
        self.clock = clock  # injectable so tests don't have to wait real seconds
        self.requestTimesByClient: dict[str, deque[float]] = {}
        self.requestsSinceCleanup = 0
        self.lock = Lock()  # uvicorn can run handlers in parallel threads

    def checkRequest(self, clientKey: str) -> float | None:
        """Record a request. Returns None if allowed, or seconds to wait if blocked."""
        now = self.clock()
        windowStart = now - self.windowSeconds
        with self.lock:
            self.requestsSinceCleanup += 1
            if self.requestsSinceCleanup >= cleanupEveryRequests:
                self.removeIdleClients(windowStart)

            requestTimes = self.requestTimesByClient.setdefault(clientKey, deque())
            while requestTimes and requestTimes[0] <= windowStart:
                requestTimes.popleft()

            if len(requestTimes) >= self.maxRequests:
                return requestTimes[0] + self.windowSeconds - now

            requestTimes.append(now)
            return None

    def removeIdleClients(self, windowStart: float) -> None:
        idleClients = [
            clientKey for clientKey, requestTimes in self.requestTimesByClient.items()
            if not requestTimes or requestTimes[-1] <= windowStart
        ]
        for clientKey in idleClients:
            del self.requestTimesByClient[clientKey]
        self.requestsSinceCleanup = 0


def getClientIp(request: Request, trustProxyHeaders: bool) -> str:
    """
    Find the caller's IP address.

    Behind Cloud Run, the connection comes from Google's proxy, and the
    real client IP is added to the end of the X-Forwarded-For header.
    Earlier entries can be typed in by the client, so they are ignored.
    Proxy headers are only trusted when configured, because locally anyone
    could send a fake X-Forwarded-For to dodge the limit.
    """
    if trustProxyHeaders:
        forwardedFor = request.headers.get("x-forwarded-for", "")
        forwardedIps = [ipText.strip() for ipText in forwardedFor.split(",") if ipText.strip()]
        if forwardedIps:
            return forwardedIps[-1]
    return request.client.host if request.client else "unknown"


@lru_cache
def getRateLimiter() -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(maxRequests=getSettings().rateLimitPerMinute)


def enforceRateLimit(
    request: Request,
    rateLimiter: SlidingWindowRateLimiter = Depends(getRateLimiter),
) -> None:
    """FastAPI dependency: add to any endpoint that should be rate limited."""
    clientIp = getClientIp(request, getSettings().trustProxyHeaders)
    retryAfterSeconds = rateLimiter.checkRequest(clientIp)
    if retryAfterSeconds is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a minute and try again.",
            headers={"Retry-After": str(max(1, math.ceil(retryAfterSeconds)))},
        )
