"""Tests for the CSV market rent provider and the HUD loader script."""

import csv
from pathlib import Path
import sys

import pytest

from app.services.marketRents import CsvMarketRentProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from loadMarketRents import (  # noqa: E402
    convertFile,
    fiscalYearInNamePattern,
    guessFiscalYear,
    parseDollarsToCents,
)


def writeCsv(filePath: Path, rows: list[list[object]]) -> None:
    with filePath.open("w", newline="", encoding="utf-8") as csvFile:
        csv.writer(csvFile).writerows(rows)


# ---------------------------------------------------------------------
# CsvMarketRentProvider
# ---------------------------------------------------------------------
def testProviderLooksUpRent(tmp_path):
    csvPath = tmp_path / "rents.csv"
    writeCsv(csvPath, [
        ["zipCode", "bedrooms", "monthlyRentCents", "fiscalYear", "dataSource"],
        ["90001", "2", "200000", "2027", "hud_safmr"],
    ])
    provider = CsvMarketRentProvider(csvPath)
    assert provider.isLoaded
    assert provider.getMarketRent("90001", 2).monthlyRentCents == 200000
    assert provider.getMarketRent("90001", 3) is None


def testProviderKeepsNewestFiscalYear(tmp_path):
    csvPath = tmp_path / "rents.csv"
    writeCsv(csvPath, [
        ["zipCode", "bedrooms", "monthlyRentCents", "fiscalYear", "dataSource"],
        ["90001", "2", "210000", "2027", "hud_safmr"],
        ["90001", "2", "190000", "2026", "hud_safmr"],
    ])
    assert CsvMarketRentProvider(csvPath).getMarketRent("90001", 2).fiscalYear == 2027


def testProviderCapsBedroomsAtFour(tmp_path):
    csvPath = tmp_path / "rents.csv"
    writeCsv(csvPath, [
        ["zipCode", "bedrooms", "monthlyRentCents", "fiscalYear", "dataSource"],
        ["90001", "4", "300000", "2027", "hud_safmr"],
    ])
    assert CsvMarketRentProvider(csvPath).getMarketRent("90001", 7).bedrooms == 4


def testMissingFileMeansNotLoaded(tmp_path):
    assert CsvMarketRentProvider(tmp_path / "missing.csv").isLoaded is False


# ---------------------------------------------------------------------
# Loader script (HUD file -> marketRents.csv)
# ---------------------------------------------------------------------
def testLoaderHandlesHudStyleHeaders(tmp_path):
    hudFile = tmp_path / "fy2027_safmrs.csv"
    writeCsv(hudFile, [
        ["FY2027 Small Area FMRs"],                                   # title row above header
        ["ZIP\nCode", "HUD Area Name", "SAFMR\n0BR", "SAFMR\n0BR -\n90%\nPayment\nStandard", "SAFMR\n2BR"],
        ["2134", "Boston", "$2,100", "$1,890", "2,800"],             # ZIP lost its leading zero
        ["90001", "Los Angeles", "1500", "1350", ""],                 # blank 2BR value
    ])
    outputPath = tmp_path / "marketRents.csv"
    writtenCount = convertFile(hudFile, outputPath, 2027)

    with outputPath.open(newline="", encoding="utf-8") as csvFile:
        rows = list(csv.DictReader(csvFile))
    assert writtenCount == 3
    assert {"zipCode": "02134", "bedrooms": "0", "monthlyRentCents": "210000",
            "fiscalYear": "2027", "dataSource": "hud_safmr"} in rows
    assert any(row["zipCode"] == "02134" and row["monthlyRentCents"] == "280000" for row in rows)
    # The 90% payment standard column must be ignored
    assert not any(row["monthlyRentCents"] == "189000" for row in rows)


def testParseDollarsToCents():
    assert parseDollarsToCents("$1,234") == 123400
    assert parseDollarsToCents(1500) == 150000
    assert parseDollarsToCents("") is None
    assert parseDollarsToCents("n/a") is None
    assert parseDollarsToCents("0") is None


def testBundledDataLoads():
    """The CSV committed to the repo must stay valid, whatever year it holds."""
    bundledPath = Path(__file__).resolve().parent.parent / "data" / "marketRents.csv"
    provider = CsvMarketRentProvider(bundledPath)
    assert provider.isLoaded
    costaMesaTwoBedroom = provider.getMarketRent("92628", 2)
    assert costaMesaTwoBedroom is not None
    assert 100000 < costaMesaTwoBedroom.monthlyRentCents < 1000000


@pytest.mark.parametrize(
    ("fileName", "expectedYear"),
    [("FY27_safmrs.xlsx", 2027), ("fy2027_safmrs.xlsx", 2027), ("SAFMR FY 2026.xlsx", 2026)],
)
def testFiscalYearGuessedFromFileName(fileName, expectedYear):
    yearMatch = fiscalYearInNamePattern.search(fileName)
    assert guessFiscalYear(yearMatch.group(1)) == expectedYear
