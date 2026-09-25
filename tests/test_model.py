from clipqc.model import (
    DetectorResult,
    Finding,
    Severity,
    Status,
    status_from_findings,
    with_findings,
    worst,
)


def f(sev: Severity) -> Finding:
    return Finding(code="x.y", severity=sev, message="m")


def test_status_from_findings_takes_the_worst_severity():
    assert status_from_findings([]) is Status.PASS
    assert status_from_findings([f(Severity.INFO)]) is Status.PASS
    assert status_from_findings([f(Severity.INFO), f(Severity.WARN)]) is Status.WARN
    assert status_from_findings([f(Severity.WARN), f(Severity.FAIL)]) is Status.FAIL


def test_worst_orders_fail_error_inconclusive_warn_pass():
    assert worst([Status.PASS, Status.WARN]) is Status.WARN
    assert worst([Status.WARN, Status.INCONCLUSIVE]) is Status.INCONCLUSIVE
    assert worst([Status.INCONCLUSIVE, Status.ERROR]) is Status.ERROR
    assert worst([Status.ERROR, Status.FAIL]) is Status.FAIL


def test_worst_ignores_skipped_unless_everything_was_skipped():
    assert worst([Status.SKIPPED, Status.PASS]) is Status.PASS
    assert worst([Status.SKIPPED, Status.SKIPPED]) is Status.SKIPPED
    assert worst([]) is Status.SKIPPED


def test_with_findings_raises_but_never_lowers_status():
    base = DetectorResult("frame", Status.INCONCLUSIVE)
    raised = with_findings(base, [f(Severity.FAIL)])
    assert raised.status is Status.FAIL
    kept = with_findings(base, [f(Severity.WARN)])
    assert kept.status is Status.INCONCLUSIVE
    assert len(kept.findings) == 1


def test_with_findings_leaves_skipped_results_alone():
    base = DetectorResult("audio", Status.SKIPPED, reason="no container")
    assert with_findings(base, [f(Severity.FAIL)]) == base
