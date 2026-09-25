"""Orchestration: find clips, extract observations once, judge each detector in isolation."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from clipqc.batch import judge_batch
from clipqc.config import Config
from clipqc.decode import DecodeObs, run_decode
from clipqc.detectors.audio import judge_audio
from clipqc.detectors.frame import judge_frame
from clipqc.model import ClipResult, DetectorResult, Status, with_findings, worst
from clipqc.probe import ProbeObs, run_probe
from clipqc.reconcile import reconcile

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
JUDGES = {"frame": judge_frame, "audio": judge_audio}
DETECTORS = tuple(JUDGES)

ProbeFn = Callable[[Path], ProbeObs]
DecodeFn = Callable[[Path, ProbeObs], DecodeObs]


def discover(root: Path) -> list[Path]:
    """Video files under root, sorted, skipping hidden files and directories."""
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
        and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )


def _error(detector: str, exc: BaseException, path: Path, rel: str) -> DetectorResult:
    """Tool failure. The reason names the clip by its relative path, never the absolute one."""
    reason = f"{type(exc).__name__}: {exc}"
    for full in sorted({str(path), str(path.absolute()), str(path.resolve())}, key=len,
                       reverse=True):
        reason = reason.replace(full, rel)
    return DetectorResult(detector, Status.ERROR, reason=reason)


def check_clips(
    root: Path,
    clips: Iterable[Path],
    cfg: Config,
    detectors: Iterable[str] = DETECTORS,
    probe_fn: ProbeFn | None = None,
    decode_fn: DecodeFn | None = None,
    on_clip: Callable[[str], None] | None = None,
) -> list[ClipResult]:
    # Resolved at call time so tests can monkeypatch clipqc.runner.run_probe/run_decode.
    probe_fn = probe_fn or run_probe
    decode_fn = decode_fn or run_decode
    detectors = tuple(detectors)
    rows: list[tuple[str, ProbeObs | None, dict[str, DetectorResult]]] = []
    for path in clips:
        rel = path.relative_to(root).as_posix()
        if on_clip:
            on_clip(rel)
        try:
            probe = probe_fn(path)
        except Exception as exc:  # the tool itself failed, not the clip
            rows.append((rel, None, {d: _error(d, exc, path, rel) for d in detectors}))
            continue
        decode: DecodeObs | None = None
        decode_exc: BaseException | None = None
        if probe.readable and (probe.video or probe.audio):
            try:
                decode = decode_fn(path, probe)
            except Exception as exc:
                decode_exc = exc
        results: dict[str, DetectorResult] = {}
        for name in detectors:
            try:
                result = JUDGES[name](probe, decode, cfg)
            except Exception as exc:
                result = _error(name, exc, path, rel)
            if decode_exc is not None and result.status is Status.INCONCLUSIVE:
                result = _error(name, decode_exc, path, rel)
            results[name] = result
        if not probe.readable and "frame" not in results:
            # A file that cannot be opened is a delivery defect whatever --only asked for.
            results["frame"] = judge_frame(probe, None, cfg)
        rows.append((rel, probe, results))

    batch = judge_batch({rel: probe for rel, probe, _ in rows if probe is not None}) \
        if "frame" in detectors else {}
    out = []
    for rel, _probe, results in rows:
        if rel in batch:
            results["frame"] = with_findings(results["frame"], batch[rel])
        results = reconcile(results)
        out.append(ClipResult(rel, worst(r.status for r in results.values()), results))
    return out
