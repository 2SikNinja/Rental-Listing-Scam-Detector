"""
Shared types for every detection check.

Each check looks at a listing and returns a CheckOutcome: whether it was
able to run, and the signals (red flags) it found. Checks do not assign
points or decide the risk level. That is the scoring engine's job, so
weights can be tuned without editing any check.
"""

from dataclasses import dataclass, field
from typing import Any

from app.schemas.listing import CheckName, Severity


@dataclass(frozen=True)
class DetectedSignal:
    """One red flag found by a check, with a plain-English reason."""

    checkName: CheckName
    signalCode: str
    severity: Severity
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckOutcome:
    """
    The result of running one check.

    ran=False means the check could not run (for example, no rent was
    entered for the price check). That is different from running and
    finding nothing, and the results page reports the two differently.
    """

    checkName: CheckName
    ran: bool
    signals: list[DetectedSignal] = field(default_factory=list)
    skipReason: str | None = None
