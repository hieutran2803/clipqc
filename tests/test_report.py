import json
import math

from clipqc.config import Config
from clipqc.model import ClipResult, DetectorResult, Finding, Severity, Status
from clipqc.report import SCHEMA, exit_code, render_table, to_dict, to_json


def clip(status: Status, path="a.mp4", findings=()) -> ClipResult:
    return ClipResult(path, status, {"frame": DetectorResult("frame", status, tuple(findings))})


def test_exit_codes():
    assert exit_code([clip(Status.PASS), clip(Status.WARN), clip(Status.SKIPPED)]) == 0
    assert exit_code([clip(Status.PASS), clip(Status.FAIL)]) == 1
    assert exit_code([clip(Status.FAIL), clip(Status.INCONCLUSIVE)]) == 1
    assert exit_code([clip(Status.PASS), clip(Status.INCONCLUSIVE)]) == 3
    assert exit_code([clip(Status.ERROR)]) == 3
    assert exit_code([clip(Status.ERROR)], strict=True) == 1


def test_json_report_lists_every_clip_and_survives_infinities():
    f = Finding("audio.silent", Severity.FAIL, "silent", evidence={"peak": -math.inf})
    clips = [clip(Status.PASS, "ok.mp4"), clip(Status.FAIL, "bad.mp4", [f])]
    data = json.loads(to_json(clips, Config(), "8.1.2"))
    assert data["schema"] == SCHEMA
    assert [c["path"] for c in data["clips"]] == ["ok.mp4", "bad.mp4"]
    assert data["clips"][0]["status"] == "pass"
    finding = data["clips"][1]["detectors"]["frame"]["findings"][0]
    assert finding["evidence"]["peak"] == "-inf"
    assert data["summary"] == {"fail": 1, "pass": 1}
    assert len(data["config_hash"]) == 64


def test_config_hash_changes_with_config():
    a = to_dict([], Config(), "x")["config_hash"]
    b = to_dict([], Config(audio="optional"), "x")["config_hash"]
    assert a != b


def test_table_shows_times_codes_and_reasons():
    f = Finding("frame.black", Severity.FAIL, "black frames 1.00s-2.00s", t_start=1.0, t_end=2.0)
    skipped = DetectorResult("audio", Status.SKIPPED, reason="container cannot be read")
    c = ClipResult("x.mp4", Status.FAIL,
                   {"frame": DetectorResult("frame", Status.FAIL, (f,)), "audio": skipped})
    text = render_table([c])
    assert "FAIL" in text and "x.mp4" in text
    assert "1.00-2.00s" in text and "frame.black" in text
    assert "skipped: container cannot be read" in text
    assert text.rstrip().endswith("1 clip(s): 1 fail")
