"""Batch-level checks: a clip that differs from most of its siblings. Pure."""
from __future__ import annotations

from collections import Counter
from typing import Callable

from clipqc.model import Finding, Severity
from clipqc.probe import ProbeObs, StreamInfo

MIN_BATCH = 3


def _resolution(v: StreamInfo) -> str | None:
    if not v.width or not v.height:
        return None
    w, h = (v.height, v.width) if v.rotation % 180 else (v.width, v.height)
    return f"{w}x{h}"


def _fps(v: StreamInfo) -> str | None:
    return f"{v.fps:.2f}" if v.fps else None


def _rotation(v: StreamInfo) -> str:
    return str(v.rotation % 360)


_ATTRIBUTES: dict[str, Callable[[StreamInfo], str | None]] = {
    "resolution": _resolution,
    "fps": _fps,
    "rotation": _rotation,
}


def judge_batch(probes: dict[str, ProbeObs]) -> dict[str, tuple[Finding, ...]]:
    videos = {p: o.video for p, o in probes.items() if o.readable and o.video}
    if len(videos) < MIN_BATCH:
        return {}
    found: dict[str, list[Finding]] = {}
    for attribute, value_of in _ATTRIBUTES.items():
        values = {p: value_of(v) for p, v in videos.items()}
        values = {p: x for p, x in values.items() if x is not None}
        if len(values) < MIN_BATCH:
            continue
        majority, count = Counter(values.values()).most_common(1)[0]
        if count * 2 <= len(values) or count == len(values):
            continue
        for path, value in values.items():
            if value != majority:
                found.setdefault(path, []).append(Finding(
                    "frame.batch_mismatch", Severity.WARN,
                    f"{attribute} {value} differs from the batch majority {majority} "
                    f"({count}/{len(values)} clips)",
                    evidence={"attribute": attribute, "value": value, "majority": majority}))
    return {p: tuple(fs) for p, fs in found.items()}
