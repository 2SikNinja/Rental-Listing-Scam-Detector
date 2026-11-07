"""
Evaluate the detector on the labeled listings in eval/labeledListings.csv.

Runs every listing through the SAME analysis pipeline the API uses
(runAnalysis), with the real HUD rent data and the real weights.yaml.

What can and can't be evaluated offline:
  - price, text wording, and throwaway-email checks run normally
  - address (needs the Census service), photos (none in the dataset), and
    cross-listing reuse (needs a database of earlier listings) are skipped
So these numbers describe the core checks, not the full live system.

Usage (from apps/api):
    uv run python scripts/evaluateDetector.py            # dev split (for tuning)
    uv run python scripts/evaluateDetector.py --split test
    uv run python scripts/evaluateDetector.py --split all

Writes eval/results-<split>.md and eval/predictions-<split>.csv.
"""

import argparse
from collections import Counter
import csv
import os
from pathlib import Path
import sys

# Offline, deterministic settings. These must be set before importing the
# app, and never point at real services or the real database.
os.environ.update({
    "APP_ENV": "test",
    "GEOCODING_PROVIDER": "none",
    "PERSISTENCE_ENABLED": "false",
    "DATABASE_URL": "postgresql://unused@localhost/unused",
    "SUPABASE_URL": "http://localhost",
    "CONTACT_HASH_SECRET": "0" * 64,
})
apiRootDir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(apiRootDir))

from app.evaluation.metrics import (  # noqa: E402
    countConfusion, f1Score, falsePositiveRate, precision, recall, wilsonInterval,
)
from app.routers.analyze import AnalysisSources, runAnalysis  # noqa: E402
from app.schemas.listing import ListingSubmission  # noqa: E402
from app.scoring.engine import getScoringConfig  # noqa: E402
from app.services.marketRents import getMarketRentProvider  # noqa: E402

repoRootDir = apiRootDir.parent.parent
datasetPath = repoRootDir / "eval" / "labeledListings.csv"
flaggedLevels = {"medium", "high"}


def buildSubmission(row: dict) -> ListingSubmission:
    def optional(fieldName: str) -> str | None:
        return row[fieldName].strip() or None

    return ListingSubmission.model_validate({
        "title": optional("title"),
        "description": row["description"],
        "monthlyRent": optional("monthlyRent"),
        "bedrooms": int(row["bedrooms"]) if row["bedrooms"].strip() else None,
        "address": {"street": optional("street"), "city": optional("city"),
                    "stateCode": optional("stateCode"), "zipCode": optional("zipCode")},
        "contact": {"email": optional("contactEmail"), "phone": optional("contactPhone")},
    })


def formatRate(rateValue: float | None) -> str:
    return "n/a" if rateValue is None else f"{rateValue:.0%}"


def formatInterval(successes: int, trials: int) -> str:
    interval = wilsonInterval(successes, trials)
    return "n/a" if interval is None else f"{interval[0]:.0%} to {interval[1]:.0%}"


def runEvaluation(split: str) -> list[dict]:
    """Run every listing in the split through the real pipeline. Returns one prediction per listing."""
    with datasetPath.open(newline="", encoding="utf-8") as datasetFile:
        rows = [row for row in csv.DictReader(datasetFile) if split == "all" or row["split"] == split]

    scoringConfig = getScoringConfig()
    sources = AnalysisSources(
        marketRentProvider=getMarketRentProvider(), scoringConfig=scoringConfig, connectionPool=None,
        photoMatcher=None, crossListingFinder=None, geocoder=None, saleListingLookup=None, phoneLineTypeLookup=None,
    )

    predictions = []
    for row in rows:
        result = runAnalysis(buildSubmission(row), [], sources)
        predictions.append({
            "id": row["id"], "label": row["label"], "riskLevel": result.riskLevel,
            "totalPoints": result.totalPoints, "flagged": result.riskLevel in flaggedLevels,
            "signals": [signal.signalCode for signal in result.signals],
            "checksRun": result.checksRun, "notes": row["notes"],
        })
    return predictions


def main() -> None:
    argumentParser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    argumentParser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parsedArgs = argumentParser.parse_args()

    scoringConfig = getScoringConfig()
    predictions = runEvaluation(parsedArgs.split)
    actualIsScam = [prediction["label"] == "scam" for prediction in predictions]
    predictedFlagged = [prediction["flagged"] for prediction in predictions]
    counts = countConfusion(actualIsScam, predictedFlagged)
    scamCount, legitCount = sum(actualIsScam), len(actualIsScam) - sum(actualIsScam)

    # How often each signal fires on scams vs honest listings (its "discrimination")
    signalsByLabel = {"scam": Counter(), "legit": Counter()}
    for prediction in predictions:
        signalsByLabel[prediction["label"]].update(set(prediction["signals"]))
    allSignalCodes = sorted(set(signalsByLabel["scam"]) | set(signalsByLabel["legit"]))

    # Threshold sweep: what if "flagged" meant a different number of points?
    sweepRows = []
    for pointThreshold in (5, 10, 15, 20, 25, 30, 35, 40, 50, 65):
        sweepCounts = countConfusion(actualIsScam, [p["totalPoints"] >= pointThreshold for p in predictions])
        sweepRows.append(f"| {pointThreshold} | {formatRate(precision(sweepCounts))} | {formatRate(recall(sweepCounts))} "
                         f"| {sweepCounts.falsePositives} of {legitCount} |")

    riskLevelCounts = Counter((p["label"], p["riskLevel"]) for p in predictions)
    reportLines = [
        f"# Evaluation results: {parsedArgs.split} split",
        "",
        f"Scoring config `{scoringConfig.version}`. {len(predictions)} listings: {scamCount} scams, {legitCount} legitimate.",
        "\"Flagged\" means a Medium or High result. Offline run: address, photo, and cross-listing checks are skipped.",
        "",
        "## Confusion matrix",
        "",
        "| | Flagged | Not flagged |",
        "|---|---|---|",
        f"| **Scam** | {counts.truePositives} (caught) | {counts.falseNegatives} (missed) |",
        f"| **Legitimate** | {counts.falsePositives} (false alarm) | {counts.trueNegatives} (correctly passed) |",
        "",
        "## Metrics (with 95% confidence intervals)",
        "",
        "| Metric | Value | 95% interval |",
        "|---|---|---|",
        f"| Recall (scams caught) | {formatRate(recall(counts))} | {formatInterval(counts.truePositives, scamCount)} |",
        f"| Precision (flags that were scams) | {formatRate(precision(counts))} "
        f"| {formatInterval(counts.truePositives, counts.truePositives + counts.falsePositives)} |",
        f"| False alarm rate (honest listings flagged) | {formatRate(falsePositiveRate(counts))} "
        f"| {formatInterval(counts.falsePositives, legitCount)} |",
        f"| F1 | {formatRate(f1Score(counts))} | |",
        "",
        "## Risk levels by label",
        "",
        "| Label | High | Medium | Low | Not enough info |",
        "|---|---|---|---|---|",
        *(f"| {label} | {riskLevelCounts[(label, 'high')]} | {riskLevelCounts[(label, 'medium')]} "
          f"| {riskLevelCounts[(label, 'low')]} | {riskLevelCounts[(label, 'insufficient_data')]} |"
          for label in ("scam", "legit")),
        "",
        "## How often each signal fires",
        "",
        f"| Signal | Scams (of {scamCount}) | Legitimate (of {legitCount}) |",
        "|---|---|---|",
        *(f"| `{code}` | {signalsByLabel['scam'][code]} | {signalsByLabel['legit'][code]} |" for code in allSignalCodes),
        "",
        "## Threshold sweep",
        "",
        "| Flag at points >= | Precision | Recall | False alarms |",
        "|---|---|---|---|",
        *sweepRows,
        "",
        "## Every listing",
        "",
        "| ID | Label | Result | Points | Signals |",
        "|---|---|---|---|---|",
        *(f"| {p['id']} | {p['label']} | {p['riskLevel']}{' ❌' if p['flagged'] != (p['label'] == 'scam') else ''} "
          f"| {p['totalPoints']} | {', '.join(p['signals']) or 'none'} |" for p in predictions),
    ]

    resultsPath = repoRootDir / "eval" / f"results-{parsedArgs.split}.md"
    resultsPath.write_text("\n".join(reportLines) + "\n", encoding="utf-8")
    with (repoRootDir / "eval" / f"predictions-{parsedArgs.split}.csv").open("w", newline="", encoding="utf-8") as outputFile:
        csvWriter = csv.writer(outputFile)
        csvWriter.writerow(["id", "label", "riskLevel", "totalPoints", "flagged", "signals", "checksRun"])
        for p in predictions:
            csvWriter.writerow([p["id"], p["label"], p["riskLevel"], p["totalPoints"], p["flagged"],
                                ";".join(p["signals"]), ";".join(p["checksRun"])])

    print(f"{parsedArgs.split}: recall {formatRate(recall(counts))}, precision {formatRate(precision(counts))}, "
          f"false alarms {counts.falsePositives}/{legitCount}  ->  {resultsPath.relative_to(repoRootDir)}")


if __name__ == "__main__":
    main()
