import shutil

import pytest

import clipqc.runner as runner
from clipqc.config import Config
from clipqc.model import Status
from clipqc.runner import check_clips, discover

EXPECTED = {
    "avmis.mp4": Status.FAIL,
    "black.mp4": Status.FAIL,
    "clean.mkv": Status.PASS,
    "clean.mp4": Status.PASS,
    "clipped.mp4": Status.FAIL,
    "corrupt.mp4": Status.FAIL,
    "cover.mp4": Status.PASS,
    "frozen.mp4": Status.WARN,
    "landscape.mp4": Status.WARN,
    "mixcs.mp4": Status.WARN,
    "moovend.mp4": Status.WARN,
    "noaudio.mp4": Status.FAIL,
    "novideo.mp4": Status.FAIL,
    "silent.mp4": Status.FAIL,
    "tiny.mp4": Status.FAIL,
    "trunc.mp4": Status.FAIL,
    "trunc_moovend.mp4": Status.FAIL,
}


def test_every_fixture_gets_its_expected_verdict(media):
    results = check_clips(media, discover(media), Config())
    assert {r.path: r.status for r in results} == EXPECTED


def test_discover_is_recursive_sorted_and_skips_hidden_and_non_video(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / ".cache").mkdir()
    for name in ("b/2.MP4", "a.mov", ".cache/x.mp4", "notes.txt", ".hidden.mp4"):
        (tmp_path / name).write_bytes(b"")
    assert [p.relative_to(tmp_path).as_posix() for p in discover(tmp_path)] == ["a.mov", "b/2.MP4"]


def one_clip(tmp_path, media, name="clean.mp4"):
    shutil.copy(media / name, tmp_path / name)
    return tmp_path, [tmp_path / name]


def test_probe_crash_makes_every_detector_error(tmp_path, media):
    root, clips = one_clip(tmp_path, media)

    def boom(path):
        raise OSError("ffprobe vanished")

    [clip] = check_clips(root, clips, Config(), probe_fn=boom)
    assert clip.status is Status.ERROR
    assert {r.status for r in clip.detectors.values()} == {Status.ERROR}
    assert "ffprobe vanished" in clip.detectors["frame"].reason


def test_decode_crash_errors_decode_dependent_detectors(tmp_path, media, monkeypatch):
    root, clips = one_clip(tmp_path, media)

    def boom(path, probe):
        raise RuntimeError("decoder died")

    monkeypatch.setattr(runner, "run_decode", boom)
    [clip] = check_clips(root, clips, Config())
    assert clip.detectors["frame"].status is Status.ERROR
    assert clip.detectors["audio"].status is Status.ERROR
    assert "decoder died" in clip.detectors["audio"].reason


def test_decode_crash_keeps_container_failures(tmp_path, media, monkeypatch):
    root, clips = one_clip(tmp_path, media, "trunc.mp4")
    monkeypatch.setattr(runner, "run_decode", lambda p, o: (_ for _ in ()).throw(RuntimeError()))
    [clip] = check_clips(root, clips, Config())
    assert clip.detectors["frame"].status is Status.FAIL


def test_one_detector_crashing_does_not_hide_the_others(tmp_path, media, monkeypatch):
    root, clips = one_clip(tmp_path, media, "black.mp4")

    def boom(probe, decode, cfg):
        raise ValueError("bug in audio judge")

    monkeypatch.setitem(runner.JUDGES, "audio", boom)
    [clip] = check_clips(root, clips, Config())
    assert clip.detectors["audio"].status is Status.ERROR
    assert clip.detectors["frame"].status is Status.FAIL
    assert clip.status is Status.FAIL


def test_only_runs_the_requested_detectors(tmp_path, media):
    root, clips = one_clip(tmp_path, media, "silent.mp4")
    [clip] = check_clips(root, clips, Config(), detectors=("frame",))
    assert list(clip.detectors) == ["frame"]
    assert clip.status is Status.PASS


@pytest.mark.parametrize("name", ["clean.mp4"])
def test_paths_in_results_are_relative(tmp_path, media, name):
    (tmp_path / "sub").mkdir()
    shutil.copy(media / name, tmp_path / "sub" / name)
    [clip] = check_clips(tmp_path, discover(tmp_path), Config())
    assert clip.path == f"sub/{name}"
