"""judge() functions must not touch the filesystem or spawn processes."""
import builtins
import pathlib
import subprocess

import pytest
from factories import decode, probe

from clipqc.batch import judge_batch
from clipqc.config import Config
from clipqc.detectors.audio import judge_audio
from clipqc.detectors.frame import judge_frame
from clipqc.model import DetectorResult, Status
from clipqc.reconcile import reconcile


@pytest.fixture
def no_io(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("I/O inside a pure judge")

    monkeypatch.setattr(builtins, "open", boom)
    for name in ("open", "read_text", "read_bytes", "stat", "exists"):
        monkeypatch.setattr(pathlib.Path, name, boom)
    for name in ("run", "Popen", "check_output", "call"):
        monkeypatch.setattr(subprocess, name, boom)


def test_judges_are_pure(no_io):
    cfg = Config()
    judge_frame(probe(), decode(black=((1.0, 2.0),), freeze=((5.0, None),)), cfg)
    judge_frame(probe(readable=False, error="x"), None, cfg)
    judge_audio(probe(), decode(integrated_lufs=-50.0), cfg)
    judge_batch({"a": probe(), "b": probe(), "c": probe()})
    reconcile({"frame": DetectorResult("frame", Status.PASS)})
