import json
import shutil

import pytest

import clipqc.runner as runner
from clipqc.cli import main


def batch(tmp_path, media, *names):
    for i, name in enumerate(names):
        shutil.copy(media / name, tmp_path / f"{i:02d}-{name}")
    return str(tmp_path)


def test_clean_batch_exits_0(tmp_path, media, capsys):
    assert main(["check", batch(tmp_path, media, "clean.mp4", "clean.mp4")]) == 0
    assert "PASS" in capsys.readouterr().out


def test_any_fail_exits_1(tmp_path, media):
    assert main(["check", batch(tmp_path, media, "clean.mp4", "black.mp4")]) == 1


def test_every_clip_unreadable_exits_1(tmp_path, media):
    assert main(["check", batch(tmp_path, media, "trunc_moovend.mp4", "trunc_moovend.mp4")]) == 1


def test_unexamined_clips_exit_3_or_1_when_strict(tmp_path, media, monkeypatch):
    def boom(path, probe):
        raise RuntimeError("decoder died")

    monkeypatch.setattr(runner, "run_decode", boom)
    root = batch(tmp_path, media, "clean.mp4")
    assert main(["check", root]) == 3
    assert main(["check", root, "--strict"]) == 1


def test_awkward_file_names_are_not_read_as_ffmpeg_options(tmp_path, media, monkeypatch, capsys):
    shutil.copy(media / "clean.mp4", tmp_path / "-intro clip:1.mp4")
    monkeypatch.chdir(tmp_path)
    assert main(["check", "."]) == 0
    assert "-intro clip:1.mp4" in capsys.readouterr().out


def test_json_goes_to_stdout_and_progress_to_stderr(tmp_path, media, capsys):
    main(["check", batch(tmp_path, media, "clean.mp4", "moovend.mp4"), "--json"])
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["summary"] == {"pass": 1, "warn": 1}
    assert "checking" in err
    assert str(tmp_path) not in out


@pytest.mark.parametrize(
    "extra, message",
    [(["--only", "text"], "unknown detector"), (["--only", ","], "unknown detector"),
     (["--config", "missing.toml"], "cannot read config")],
)
def test_usage_errors_exit_2(tmp_path, media, capsys, extra, message):
    assert main(["check", batch(tmp_path, media, "clean.mp4"), *extra]) == 2
    assert message in capsys.readouterr().err


def test_missing_directory_exits_2(tmp_path):
    assert main(["check", str(tmp_path / "nope")]) == 2


def test_directory_without_videos_exits_2(tmp_path, capsys):
    (tmp_path / "readme.txt").write_text("x")
    assert main(["check", str(tmp_path)]) == 2
    assert "no video files" in capsys.readouterr().err


def test_missing_ffmpeg_exits_2(tmp_path, media, monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda tool: None)
    assert main(["check", batch(tmp_path, media, "clean.mp4")]) == 2
    assert "ffmpeg" in capsys.readouterr().err


def test_doctor_reports_ffmpeg(capsys):
    assert main(["doctor"]) == 0
    assert "ffmpeg version:" in capsys.readouterr().out


def test_doctor_without_ffmpeg_exits_2(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda tool: None)
    assert main(["doctor"]) == 2
