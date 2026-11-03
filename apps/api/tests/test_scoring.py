"""
Tests for app/scoring/engine.py and safetyTips.py.

A small fixed config is used (not weights.yaml), so these tests check
the engine's logic and keep passing when the real weights are tuned.
"""

from pathlib import Path

from pydantic import ValidationError
import pytest

from app.checks.base import CheckOutcome, DetectedSignal
from app.scoring.engine import ScoringConfig, loadScoringConfig, scoreOutcomes
from app.scoring.safetyTips import buildSafetyTips, generalTips, signalTips

testConfigValues = {
    "version": "test-1",
    "severityPoints": {"info": 0, "low": 5, "medium": 15, "high": 30},
    "signalPointOverrides": {"SPECIAL_CODE": 40},
    "maxPointsPerCheck": {"text": 50},
    "riskThresholds": {"medium": 20, "high": 50},
    "minimumChecksForLowRisk": 2,
}
testConfig = ScoringConfig.model_validate(testConfigValues)


def makeSignal(signalCode: str, severity: str, checkName: str = "text") -> DetectedSignal:
    return DetectedSignal(checkName=checkName, signalCode=signalCode, severity=severity, explanation="test")


def ranOutcome(checkName: str, *signals: DetectedSignal) -> CheckOutcome:
    return CheckOutcome(checkName=checkName, ran=True, signals=list(signals))


def skippedOutcome(checkName: str) -> CheckOutcome:
    return CheckOutcome(checkName=checkName, ran=False, skipReason="missing data")


# ---------------------------------------------------------------------
# Points
# ---------------------------------------------------------------------
def testPointsComeFromSeverity():
    result = scoreOutcomes([ranOutcome("text", makeSignal("A_CODE", "medium")), ranOutcome("price")], testConfig)
    assert result.scoredSignals[0].points == 15
    assert result.totalPoints == 15


def testOverrideReplacesSeverityPoints():
    result = scoreOutcomes([ranOutcome("text", makeSignal("SPECIAL_CODE", "low"))], testConfig)
    assert result.totalPoints == 40


def testSignalsAreSortedMostSeriousFirst():
    result = scoreOutcomes(
        [ranOutcome("text", makeSignal("LOW_ONE", "low"), makeSignal("HIGH_ONE", "high"))], testConfig
    )
    assert [item.signal.signalCode for item in result.scoredSignals] == ["HIGH_ONE", "LOW_ONE"]


# ---------------------------------------------------------------------
# Per-check cap
# ---------------------------------------------------------------------
def testCapLimitsOneCheckButKeepsEverySignalVisible():
    textOutcome = ranOutcome("text", *(makeSignal(f"CODE_{index}", "high") for index in range(3)))  # 90 raw
    result = scoreOutcomes([textOutcome], testConfig)
    assert result.totalPoints == 50
    assert len(result.scoredSignals) == 3
    assert sorted(item.points for item in result.scoredSignals) == [0, 20, 30]


def testCapOnlyAppliesToItsOwnCheck():
    result = scoreOutcomes(
        [
            ranOutcome("text", makeSignal("T1", "high"), makeSignal("T2", "high")),   # 60, capped to 50
            ranOutcome("price", makeSignal("P1", "high", checkName="price")),        # 30, no cap
        ],
        testConfig,
    )
    assert result.totalPoints == 80


# ---------------------------------------------------------------------
# Risk levels and thresholds
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("severities", "expectedLevel"),
    [
        ([], "low"),
        (["low", "low", "low"], "low"),        # 15 points
        (["low", "medium"], "medium"),         # 20, exactly the medium line
        (["medium", "medium", "low"], "medium"),  # 35
        (["high", "medium", "low"], "high"),   # 50, exactly the high line
    ],
)
def testThresholdBoundaries(severities, expectedLevel):
    signals = [makeSignal(f"CODE_{index}", severity) for index, severity in enumerate(severities)]
    result = scoreOutcomes([ranOutcome("text", *signals), ranOutcome("price")], testConfig)
    assert result.riskLevel == expectedLevel


def testTooFewChecksGivesInsufficientDataInsteadOfLow():
    result = scoreOutcomes([ranOutcome("text"), skippedOutcome("price")], testConfig)
    assert result.riskLevel == "insufficient_data"
    assert result.checksRunCount == 1


def testRedFlagsStillShowEvenWhenChecksWereSkipped():
    """Found evidence is real, so a missing ZIP never hides a high score."""
    result = scoreOutcomes(
        [ranOutcome("text", makeSignal("H1", "high"), makeSignal("H2", "high")), skippedOutcome("price")],
        testConfig,
    )
    assert result.riskLevel == "high"


def testResultRecordsConfigVersion():
    assert scoreOutcomes([], testConfig).configVersion == "test-1"


# ---------------------------------------------------------------------
# Config validation: typos in weights.yaml must fail loudly
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "badChange",
    [
        {"riskThresholds": {"medium": 50, "high": 20}},                     # wrong order
        {"severityPoints": {"info": 0, "low": 5, "medium": 15}},           # missing "high"
        {"signalPointOverrides": {"X": -10}},                                # negative points
        {"maxPointsPerCheck": {"textt": 50}},                                # misspelled check
        {"unknownSetting": True},                                            # unknown key
    ],
)
def testInvalidConfigIsRejected(badChange):
    with pytest.raises(ValidationError):
        ScoringConfig.model_validate({**testConfigValues, **badChange})


def testBundledWeightsFileIsValid():
    weightsPath = Path(__file__).resolve().parent.parent / "app" / "scoring" / "weights.yaml"
    bundledConfig = loadScoringConfig(weightsPath)
    assert bundledConfig.version
    assert bundledConfig.riskThresholds.high > bundledConfig.riskThresholds.medium


# ---------------------------------------------------------------------
# Safety tips
# ---------------------------------------------------------------------
def testSignalSpecificTipsComeFirstThenGeneralTips():
    result = scoreOutcomes([ranOutcome("text", makeSignal("KEYS_MAILED", "high"))], testConfig)
    tips = buildSafetyTips(result.scoredSignals)
    assert tips[0] == signalTips["KEYS_MAILED"]
    assert tips[1:] == generalTips


def testNoSignalsGivesGeneralTipsOnly():
    assert buildSafetyTips([]) == generalTips
