"""
Evaluation as a regression test.

Runs the labeled dataset (eval/labeledListings.csv) through the real
pipeline on every CI run. If a rule or weight change makes the detector
miss more scams or flag more honest listings than the current baseline,
the build fails, so accuracy can't quietly get worse.

Baseline (scoring 2026-11-07.3, all 37 listings): recall 87% (13 of 15),
3 false alarms out of 22. The floors leave one listing of slack each way.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from evaluateDetector import runEvaluation  # noqa: E402

minimumScamsCaught = 12        # of 15
maximumFalseAlarms = 4         # of 22


def testDetectorAccuracyDoesNotRegress():
    predictions = runEvaluation("all")
    scamsCaught = sum(p["label"] == "scam" and p["flagged"] for p in predictions)
    falseAlarms = sum(p["label"] == "legit" and p["flagged"] for p in predictions)
    missedIds = [p["id"] for p in predictions if p["label"] == "scam" and not p["flagged"]]
    falseAlarmIds = [p["id"] for p in predictions if p["label"] == "legit" and p["flagged"]]
    assert scamsCaught >= minimumScamsCaught, f"Recall regressed. Missed: {missedIds}"
    assert falseAlarms <= maximumFalseAlarms, f"False alarms increased: {falseAlarmIds}"
