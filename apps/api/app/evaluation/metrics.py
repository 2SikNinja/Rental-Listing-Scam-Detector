"""
Classification metrics for the labeled evaluation set.

Positive class = "scam". A listing is predicted positive ("flagged") when
its risk level is medium or high.

  precision = of the listings we flagged, how many were really scams
              (low precision = honest landlords getting flagged)
  recall    = of the real scams, how many we flagged
              (low recall = scams slipping through)

With a few dozen examples, one listing can move a metric by 5 to 10
points, so every rate comes with a 95% Wilson confidence interval: the
range the true rate plausibly falls in, given how little data there is.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ConfusionCounts:
    truePositives: int    # scam, flagged
    falsePositives: int   # legit, flagged
    trueNegatives: int    # legit, not flagged
    falseNegatives: int   # scam, not flagged

    @property
    def total(self) -> int:
        return self.truePositives + self.falsePositives + self.trueNegatives + self.falseNegatives


def countConfusion(actualIsScam: list[bool], predictedFlagged: list[bool]) -> ConfusionCounts:
    if len(actualIsScam) != len(predictedFlagged):
        raise ValueError("actual and predicted lists must be the same length")
    pairs = list(zip(actualIsScam, predictedFlagged))
    return ConfusionCounts(
        truePositives=sum(actual and predicted for actual, predicted in pairs),
        falsePositives=sum((not actual) and predicted for actual, predicted in pairs),
        trueNegatives=sum((not actual) and (not predicted) for actual, predicted in pairs),
        falseNegatives=sum(actual and (not predicted) for actual, predicted in pairs),
    )


def safeRatio(numerator: int, denominator: int) -> float | None:
    """None instead of a misleading 0 when there is nothing to measure."""
    return numerator / denominator if denominator else None


def precision(counts: ConfusionCounts) -> float | None:
    return safeRatio(counts.truePositives, counts.truePositives + counts.falsePositives)


def recall(counts: ConfusionCounts) -> float | None:
    return safeRatio(counts.truePositives, counts.truePositives + counts.falseNegatives)


def falsePositiveRate(counts: ConfusionCounts) -> float | None:
    return safeRatio(counts.falsePositives, counts.falsePositives + counts.trueNegatives)


def f1Score(counts: ConfusionCounts) -> float | None:
    precisionValue, recallValue = precision(counts), recall(counts)
    if precisionValue is None or recallValue is None or precisionValue + recallValue == 0:
        return None
    return 2 * precisionValue * recallValue / (precisionValue + recallValue)


def wilsonInterval(successes: int, trials: int, zScore: float = 1.96) -> tuple[float, float] | None:
    """
    95% confidence interval for a proportion. Unlike the simple
    "p plus or minus 2 standard errors", it stays inside 0 to 1 and
    behaves sensibly with small samples or rates near 0% or 100%.
    """
    if trials == 0:
        return None
    observedRate = successes / trials
    zSquared = zScore ** 2
    center = (observedRate + zSquared / (2 * trials)) / (1 + zSquared / trials)
    margin = (zScore / (1 + zSquared / trials)) * math.sqrt(
        observedRate * (1 - observedRate) / trials + zSquared / (4 * trials ** 2)
    )
    return max(0.0, center - margin), min(1.0, center + margin)
