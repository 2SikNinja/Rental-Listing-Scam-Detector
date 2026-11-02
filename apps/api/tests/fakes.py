"""
Test doubles shared across test files.

Tests should never depend on the real HUD data in data/marketRents.csv:
that file changes every year, and results would differ between machines.
"""

from app.services.marketRents import MarketRent, maxHudBedrooms

defaultFakeRents = {0: 120000, 1: 150000, 2: 200000, 3: 260000, 4: 300000}


class FakeMarketRentProvider:
    """Typical 2BR rent is exactly $2,000 in the configured ZIP code."""

    def __init__(self, rentsByBedrooms: dict[int, int] | None = None, zipCode: str = "90001"):
        self.zipCode = zipCode
        self.rentsByBedrooms = dict(defaultFakeRents) if rentsByBedrooms is None else rentsByBedrooms

    @property
    def isLoaded(self) -> bool:
        return len(self.rentsByBedrooms) > 0

    def getMarketRent(self, zipCode: str, bedrooms: int) -> MarketRent | None:
        cappedBedrooms = min(bedrooms, maxHudBedrooms)
        if zipCode != self.zipCode or cappedBedrooms not in self.rentsByBedrooms:
            return None
        return MarketRent(zipCode, cappedBedrooms, self.rentsByBedrooms[cappedBedrooms], 2027, "hud_safmr")
