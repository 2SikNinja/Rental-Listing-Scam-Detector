"""
Market rent lookup for the price check.

Data source: HUD Small Area Fair Market Rents (SAFMR), published yearly
by the U.S. Department of Housing and Urban Development for every ZIP
code in metro areas, for 0 to 4 bedroom units. SAFMR is roughly the
40th percentile rent for a standard-quality unit, so it is a fairly
conservative "typical rent." A listing far *below* it is unusual.

The price check depends on the MarketRentProvider interface, not on a
specific data store. Today the data comes from a CSV file built by
scripts/loadMarketRents.py. Later it can come from the market_rents
table in Postgres without changing the price check, and tests can pass
in a small fake provider.
"""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import apiRootDir, getSettings

maxHudBedrooms = 4


@dataclass(frozen=True)
class MarketRent:
    zipCode: str
    bedrooms: int
    monthlyRentCents: int
    fiscalYear: int
    dataSource: str


class MarketRentProvider(Protocol):
    def getMarketRent(self, zipCode: str, bedrooms: int) -> MarketRent | None:
        """Return typical rent for this ZIP and bedroom count, or None if unknown."""
        ...

    @property
    def isLoaded(self) -> bool:
        """False when no market data is available at all."""
        ...


class CsvMarketRentProvider:
    """
    Loads the whole CSV into a dictionary once at startup.

    About 27,000 ZIP codes x 5 bedroom sizes is roughly 135,000 entries,
    a few megabytes in memory, and each lookup is instant.
    """

    def __init__(self, csvPath: Path):
        self.csvPath = csvPath
        self.rentsByKey: dict[tuple[str, int], MarketRent] = {}
        if csvPath.exists():
            self.loadCsv()

    def loadCsv(self) -> None:
        with self.csvPath.open(newline="", encoding="utf-8") as csvFile:
            for row in csv.DictReader(csvFile):
                marketRent = MarketRent(
                    zipCode=row["zipCode"],
                    bedrooms=int(row["bedrooms"]),
                    monthlyRentCents=int(row["monthlyRentCents"]),
                    fiscalYear=int(row["fiscalYear"]),
                    dataSource=row["dataSource"],
                )
                lookupKey = (marketRent.zipCode, marketRent.bedrooms)
                existingRent = self.rentsByKey.get(lookupKey)
                # If a ZIP appears more than once, keep the newest year
                if existingRent is None or marketRent.fiscalYear > existingRent.fiscalYear:
                    self.rentsByKey[lookupKey] = marketRent

    @property
    def isLoaded(self) -> bool:
        return len(self.rentsByKey) > 0

    def getMarketRent(self, zipCode: str, bedrooms: int) -> MarketRent | None:
        # HUD only publishes up to 4 bedrooms, so larger units use the 4BR figure
        return self.rentsByKey.get((zipCode, min(bedrooms, maxHudBedrooms)))


@lru_cache
def getMarketRentProvider() -> MarketRentProvider:
    """Created once and shared. FastAPI injects this into the /analyze endpoint."""
    configuredPath = Path(getSettings().marketRentsPath)
    csvPath = configuredPath if configuredPath.is_absolute() else apiRootDir / configuredPath
    return CsvMarketRentProvider(csvPath)
