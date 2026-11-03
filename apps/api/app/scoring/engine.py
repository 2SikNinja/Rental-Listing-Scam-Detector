"""
Scoring engine: turns the signals from every check into points and a
risk level.

Separation of concerns:
  - Checks decide WHAT is suspicious and how serious it is (severity).
  - The engine decides HOW MUCH each finding counts (points), using the
    weights in weights.yaml.

So weights can be tuned (Step 8, using the labeled test set) without
touching any detection code, and every result records which config
version produced it.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from app.checks.base import CheckOutcome, DetectedSignal
from app.config import apiRootDir, getSettings
from app.schemas.listing import CheckName, RiskLevel, Severity


class RiskThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medium: int = Field(gt=0)
    high: int = Field(gt=0)

    @model_validator(mode="after")
    def validateOrder(self) -> "RiskThresholds":
        if self.high <= self.medium:
            raise ValueError("riskThresholds.high must be greater than riskThresholds.medium")
        return self


class ScoringConfig(BaseModel):
    """
    The validated contents of weights.yaml. A typo in the file (unknown
    key, negative points, thresholds in the wrong order) stops the app at
    startup with a clear error instead of producing silently wrong scores.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    severityPoints: dict[Severity, int]
    signalPointOverrides: dict[str, int] = Field(default_factory=dict)
    maxPointsPerCheck: dict[CheckName, int] = Field(default_factory=dict)
    riskThresholds: RiskThresholds
    minimumChecksForLowRisk: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def validatePoints(self) -> "ScoringConfig":
        missingSeverities = {"info", "low", "medium", "high"} - set(self.severityPoints)
        if missingSeverities:
            raise ValueError(f"severityPoints is missing: {', '.join(sorted(missingSeverities))}")
        allPoints = [*self.severityPoints.values(), *self.signalPointOverrides.values(),
                     *self.maxPointsPerCheck.values()]
        if any(points < 0 for points in allPoints):
            raise ValueError("Points and caps cannot be negative")
        return self


@dataclass(frozen=True)
class ScoredSignal:
    signal: DetectedSignal
    points: int


@dataclass(frozen=True)
class ScoreResult:
    scoredSignals: list[ScoredSignal]
    totalPoints: int
    riskLevel: RiskLevel
    checksRunCount: int
    configVersion: str


def pointsForSignal(detectedSignal: DetectedSignal, scoringConfig: ScoringConfig) -> int:
    overridePoints = scoringConfig.signalPointOverrides.get(detectedSignal.signalCode)
    if overridePoints is not None:
        return overridePoints
    return scoringConfig.severityPoints[detectedSignal.severity]


def applyCheckCap(scoredSignals: list[ScoredSignal], pointCap: int | None) -> list[ScoredSignal]:
    """
    Limit one check's total. Highest-point signals keep their points
    first, and later ones are reduced (possibly to 0) once the cap is hit.
    Every signal is still shown to the user, so nothing is hidden.
    """
    if pointCap is None:
        return scoredSignals
    remainingPoints = pointCap
    cappedSignals: list[ScoredSignal] = []
    for scoredSignal in sorted(scoredSignals, key=lambda item: item.points, reverse=True):
        allowedPoints = min(scoredSignal.points, remainingPoints)
        remainingPoints -= allowedPoints
        cappedSignals.append(ScoredSignal(scoredSignal.signal, allowedPoints))
    return cappedSignals


def riskLevelFor(totalPoints: int, checksRunCount: int, scoringConfig: ScoringConfig) -> RiskLevel:
    thresholds = scoringConfig.riskThresholds
    if totalPoints >= thresholds.high:
        return "high"
    if totalPoints >= thresholds.medium:
        return "medium"
    if checksRunCount < scoringConfig.minimumChecksForLowRisk:
        return "insufficient_data"
    return "low"


def scoreOutcomes(checkOutcomes: list[CheckOutcome], scoringConfig: ScoringConfig) -> ScoreResult:
    scoredSignals: list[ScoredSignal] = []
    for outcome in checkOutcomes:
        checkSignals = [ScoredSignal(signal, pointsForSignal(signal, scoringConfig)) for signal in outcome.signals]
        scoredSignals.extend(applyCheckCap(checkSignals, scoringConfig.maxPointsPerCheck.get(outcome.checkName)))

    # Most serious first, so the results page leads with them
    scoredSignals.sort(key=lambda item: item.points, reverse=True)
    totalPoints = sum(item.points for item in scoredSignals)
    checksRunCount = sum(1 for outcome in checkOutcomes if outcome.ran)

    return ScoreResult(
        scoredSignals=scoredSignals,
        totalPoints=totalPoints,
        riskLevel=riskLevelFor(totalPoints, checksRunCount, scoringConfig),
        checksRunCount=checksRunCount,
        configVersion=scoringConfig.version,
    )


def loadScoringConfig(configPath: Path) -> ScoringConfig:
    with configPath.open(encoding="utf-8") as configFile:
        rawConfig = yaml.safe_load(configFile)  # safe_load never runs code embedded in YAML
    return ScoringConfig.model_validate(rawConfig)


@lru_cache
def getScoringConfig() -> ScoringConfig:
    """Loaded once and shared. FastAPI injects this into /analyze."""
    configuredPath = Path(getSettings().scoringConfigPath)
    configPath = configuredPath if configuredPath.is_absolute() else apiRootDir / configuredPath
    return loadScoringConfig(configPath)
