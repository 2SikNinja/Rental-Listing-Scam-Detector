"""
Convert HUD's Small Area Fair Market Rent (SAFMR) spreadsheet into the
CSV the price check reads (apps/api/data/marketRents.csv).

Usage (from apps/api):
    uv run python scripts/loadMarketRents.py path/to/fy2027_safmrs.xlsx

Where to get the file:
    huduser.gov > Datasets > Fair Market Rents > Small Area FMRs
    Download the SAFMR file for the latest fiscal year (.xlsx).

HUD's column headers change a little between years (line breaks,
spacing), so columns are found by pattern instead of exact name:
    - the ZIP code column: header starts with "zip"
    - bedroom columns: header like "SAFMR 0BR" ... "SAFMR 4BR"
      (the 90% and 110% "payment standard" columns are ignored)

The script is idempotent: running it again simply rebuilds the CSV.
"""

import argparse
import csv
from pathlib import Path
import re
import sys

apiRootDir = Path(__file__).resolve().parent.parent
defaultOutputPath = apiRootDir / "data" / "marketRents.csv"

bedroomHeaderPattern = re.compile(r"^safmr ?([0-4]) ?br$")
# Matches "fy2027", "FY 2027", and HUD's short form "FY27"
fiscalYearInNamePattern = re.compile(r"fy ?(\d{4}|\d{2})(?!\d)", re.IGNORECASE)


def normalizeHeader(rawHeader: object) -> str:
    return re.sub(r"\s+", " ", str(rawHeader or "")).strip().lower()


def parseDollarsToCents(rawValue: object) -> int | None:
    if rawValue is None or str(rawValue).strip() == "":
        return None
    cleanedValue = re.sub(r"[$,\s]", "", str(rawValue))
    try:
        dollarAmount = float(cleanedValue)
    except ValueError:
        return None
    return round(dollarAmount * 100) if dollarAmount > 0 else None


def readRows(inputPath: Path) -> list[list[object]]:
    if inputPath.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook  # dev-only dependency

        workbook = load_workbook(inputPath, read_only=True, data_only=True)
        worksheet = workbook.worksheets[0]
        return [list(row) for row in worksheet.iter_rows(values_only=True)]
    with inputPath.open(newline="", encoding="utf-8-sig") as csvFile:
        return [list(row) for row in csv.reader(csvFile)]


def findHeaderRow(allRows: list[list[object]]) -> int:
    """HUD files sometimes have title rows above the real header."""
    for rowIndex, row in enumerate(allRows[:20]):
        normalizedHeaders = [normalizeHeader(cell) for cell in row]
        hasZip = any(header.startswith("zip") for header in normalizedHeaders)
        hasBedrooms = any(bedroomHeaderPattern.match(header) for header in normalizedHeaders)
        if hasZip and hasBedrooms:
            return rowIndex
    raise ValueError("Could not find a header row with a ZIP column and 'SAFMR 0BR' style columns.")


def convertFile(inputPath: Path, outputPath: Path, fiscalYear: int) -> int:
    allRows = readRows(inputPath)
    headerRowIndex = findHeaderRow(allRows)
    normalizedHeaders = [normalizeHeader(cell) for cell in allRows[headerRowIndex]]

    zipColumnIndex = next(index for index, header in enumerate(normalizedHeaders) if header.startswith("zip"))
    bedroomColumns: dict[int, int] = {}
    for columnIndex, header in enumerate(normalizedHeaders):
        bedroomMatch = bedroomHeaderPattern.match(header)
        if bedroomMatch:
            bedroomColumns[int(bedroomMatch.group(1))] = columnIndex

    outputPath.parent.mkdir(parents=True, exist_ok=True)
    writtenCount = 0
    seenKeys: set[tuple[str, int]] = set()

    with outputPath.open("w", newline="", encoding="utf-8") as outputFile:
        csvWriter = csv.writer(outputFile)
        csvWriter.writerow(["zipCode", "bedrooms", "monthlyRentCents", "fiscalYear", "dataSource"])

        for row in allRows[headerRowIndex + 1:]:
            if zipColumnIndex >= len(row) or row[zipColumnIndex] is None:
                continue
            # Excel often stores ZIPs as numbers, dropping leading zeros (02134 -> 2134)
            zipText = re.sub(r"\D", "", str(row[zipColumnIndex]).split(".")[0]).zfill(5)
            if len(zipText) != 5:
                continue

            for bedrooms, columnIndex in sorted(bedroomColumns.items()):
                rentCents = parseDollarsToCents(row[columnIndex]) if columnIndex < len(row) else None
                # Some ZIPs span two metro areas; keep the first row HUD lists
                if rentCents is None or (zipText, bedrooms) in seenKeys:
                    continue
                seenKeys.add((zipText, bedrooms))
                csvWriter.writerow([zipText, bedrooms, rentCents, fiscalYear, "hud_safmr"])
                writtenCount += 1

    return writtenCount


def guessFiscalYear(yearText: str) -> int:
    """'2027' -> 2027 and '27' -> 2027."""
    return int(yearText) if len(yearText) == 4 else 2000 + int(yearText)


def main() -> None:
    argumentParser = argparse.ArgumentParser(description="Build data/marketRents.csv from HUD SAFMR data.")
    argumentParser.add_argument("inputFile", type=Path, help="HUD SAFMR .xlsx or .csv file")
    argumentParser.add_argument("--fiscal-year", type=int, dest="fiscalYear",
                                help="Fiscal year of the data (guessed from the file name if it contains 'fy2027')")
    argumentParser.add_argument("--output", type=Path, default=defaultOutputPath)
    parsedArgs = argumentParser.parse_args()

    fiscalYear = parsedArgs.fiscalYear
    if fiscalYear is None:
        yearMatch = fiscalYearInNamePattern.search(parsedArgs.inputFile.name)
        if not yearMatch:
            sys.exit("Could not guess the fiscal year from the file name. Pass --fiscal-year 2027.")
        fiscalYear = guessFiscalYear(yearMatch.group(1))

    writtenCount = convertFile(parsedArgs.inputFile, parsedArgs.output, fiscalYear)
    print(f"Wrote {writtenCount:,} rows (FY{fiscalYear}) to {parsedArgs.output}")


if __name__ == "__main__":
    main()
