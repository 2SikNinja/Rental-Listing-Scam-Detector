"""Tests for app/evaluation/metrics.py."""

import pytest

from app.evaluation.metrics import (
    countConfusion, f1Score, falsePositiveRate, precision, recall, wilsonInterval,
)

#                 scam  scam  scam  legit  legit  legit  legit
actualIsScam =     [True, True, True, False, False, False, False]
predictedFlagged = [True, True, False, True, False, False, False]


def testConfusionCounts():
    counts = countConfusion(actualIsScam, predictedFlagged)
    assert (counts.truePositives, counts.falseNegatives, counts.falsePositives, counts.trueNegatives) == (2, 1, 1, 3)
    assert counts.total == 7


def testRates():
    counts = countConfusion(actualIsScam, predictedFlagged)
    assert recall(counts) == pytest.approx(2 / 3)
    assert precision(counts) == pytest.approx(2 / 3)
    assert falsePositiveRate(counts) == pytest.approx(1 / 4)
    assert f1Score(counts) == pytest.approx(2 / 3)


def testNothingFlaggedGivesNoneNotZero():
    """Precision is undefined when nothing was flagged; reporting 0% would be misleading."""
    counts = countConfusion([True, False], [False, False])
    assert precision(counts) is None
    assert f1Score(counts) is None


def testMismatchedLengthsAreRejected():
    with pytest.raises(ValueError):
        countConfusion([True], [True, False])


def testWilsonIntervalKnownValue():
    # 7 of 8: the textbook 95% Wilson interval is roughly 0.53 to 0.98
    lower, upper = wilsonInterval(7, 8)
    assert lower == pytest.approx(0.529, abs=0.005)
    assert upper == pytest.approx(0.978, abs=0.005)


def testWilsonIntervalStaysInsideZeroToOne():
    lower, upper = wilsonInterval(0, 5)
    assert lower == 0.0 and 0 < upper < 1
    lower, upper = wilsonInterval(5, 5)
    assert 0 < lower < 1 and upper == 1.0


def testWilsonIntervalWithNoTrials():
    assert wilsonInterval(0, 0) is None
