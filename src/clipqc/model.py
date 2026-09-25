"""Result types shared by every detector. Pure data, no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable


class Severity(str, Enum):
    FAIL = "fail"
    WARN = "warn"
    INFO = "info"


class Status(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    t_start: float | None = None
    t_end: float | None = None
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DetectorResult:
    detector: str
    status: Status
    findings: tuple[Finding, ...] = ()
    coverage: float = 1.0
    reason: str = ""


@dataclass(frozen=True)
class ClipResult:
    path: str
    status: Status
    detectors: dict[str, DetectorResult]


# Worst first. SKIPPED is deliberately absent: it never decides a clip's status.
_RANK = {
    Status.FAIL: 4,
    Status.ERROR: 3,
    Status.INCONCLUSIVE: 2,
    Status.WARN: 1,
    Status.PASS: 0,
}


def status_from_findings(findings: Iterable[Finding]) -> Status:
    severities = {f.severity for f in findings}
    if Severity.FAIL in severities:
        return Status.FAIL
    if Severity.WARN in severities:
        return Status.WARN
    return Status.PASS


def worst(statuses: Iterable[Status]) -> Status:
    ranked = [s for s in statuses if s is not Status.SKIPPED]
    if not ranked:
        return Status.SKIPPED
    return max(ranked, key=_RANK.__getitem__)


def with_findings(result: DetectorResult, extra: Iterable[Finding]) -> DetectorResult:
    """Append findings and let them raise (never lower) the status."""
    extra = tuple(extra)
    if not extra:
        return result
    if result.status is Status.SKIPPED:
        return result
    status = worst([result.status, status_from_findings(extra)])
    return replace(result, findings=result.findings + extra, status=status)
