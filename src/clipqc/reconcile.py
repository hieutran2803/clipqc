"""Cross-detector rules, applied after every judge(). Pure."""
from __future__ import annotations

from dataclasses import replace

from clipqc.model import DetectorResult, Status


def reconcile(results: dict[str, DetectorResult]) -> dict[str, DetectorResult]:
    """A truncated file limits what every other detector could have examined."""
    frame = results.get("frame")
    if frame is None or frame.coverage >= 1.0 \
            or not any(f.code == "frame.truncated" for f in frame.findings):
        return results
    out = dict(results)
    for name, result in results.items():
        if name != "frame" and result.status is not Status.SKIPPED:
            out[name] = replace(result, coverage=min(result.coverage, frame.coverage))
    return out
