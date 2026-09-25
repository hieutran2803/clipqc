from clipqc.model import DetectorResult, Finding, Severity, Status
from clipqc.reconcile import reconcile


def test_truncation_limits_other_detectors_coverage():
    frame = DetectorResult("frame", Status.FAIL, (Finding("frame.truncated", Severity.FAIL, "m",
                                                          t_start=2.0),), coverage=0.5)
    audio = DetectorResult("audio", Status.PASS)
    out = reconcile({"frame": frame, "audio": audio})
    assert out["audio"].coverage == 0.5
    assert out["frame"] is frame


def test_skipped_detectors_are_left_alone():
    frame = DetectorResult("frame", Status.FAIL, (Finding("frame.truncated", Severity.FAIL, "m"),),
                           coverage=0.5)
    skipped = DetectorResult("audio", Status.SKIPPED, reason="x")
    assert reconcile({"frame": frame, "audio": skipped})["audio"] is skipped


def test_nothing_changes_without_truncation():
    results = {"frame": DetectorResult("frame", Status.PASS),
               "audio": DetectorResult("audio", Status.PASS)}
    assert reconcile(results) == results
