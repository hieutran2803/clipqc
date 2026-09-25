"""Report rendering (table, JSON) and the exit-code contract."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict
from enum import Enum

from clipqc import __version__
from clipqc.config import Config
from clipqc.model import ClipResult, Status

SCHEMA = "clipqc.report/v1"


def exit_code(clips: list[ClipResult], strict: bool = False) -> int:
    statuses = {c.status for c in clips}
    if Status.FAIL in statuses:
        return 1
    if statuses & {Status.ERROR, Status.INCONCLUSIVE}:
        return 1 if strict else 3
    return 0


def _plain(value):
    """JSON-safe copy: enums to values, non-finite floats to strings (JSON has no inf/nan)."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def to_dict(clips: list[ClipResult], cfg: Config, ffmpeg_version: str) -> dict:
    config = _plain(asdict(cfg))
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    return {
        "schema": SCHEMA,
        "tool": {"name": "clipqc", "version": __version__},
        "ffmpeg": {"version": ffmpeg_version},
        "config": config,
        "config_hash": config_hash,
        "clips": [_plain(asdict(c)) for c in clips],
        "summary": dict(sorted(Counter(c.status.value for c in clips).items())),
    }


def to_json(clips: list[ClipResult], cfg: Config, ffmpeg_version: str) -> str:
    return json.dumps(to_dict(clips, cfg, ffmpeg_version), indent=2, allow_nan=False)


def _when(t_start: float | None, t_end: float | None) -> str:
    if t_start is None:
        return "-"
    if t_end is None or t_end == t_start:
        return f"{t_start:.2f}s"
    return f"{t_start:.2f}-{t_end:.2f}s"


def render_table(clips: list[ClipResult]) -> str:
    lines = []
    for clip in clips:
        lines.append(f"{clip.status.value.upper():<12} {clip.path}")
        for result in clip.detectors.values():
            for f in result.findings:
                lines.append(f"  {f.severity.value:<5} {_when(f.t_start, f.t_end):<14} "
                             f"{f.code:<27} {f.message}")
            if result.status in (Status.ERROR, Status.INCONCLUSIVE, Status.SKIPPED) \
                    and result.reason:
                lines.append(f"  {'-':<5} {'-':<14} {result.detector:<27} "
                             f"{result.status.value}: {result.reason}")
    counts = Counter(c.status.value for c in clips)
    lines.append("")
    lines.append(f"{len(clips)} clip(s): " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    return "\n".join(lines)
