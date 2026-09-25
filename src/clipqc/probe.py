"""Container facts from ffprobe (no decoding) plus the MP4 box walk."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from clipqc.boxes import BoxWalk, walk_boxes

_ENTRIES = (
    "format=duration"
    ":stream=index,codec_type,codec_name,width,height,avg_frame_rate,"
    "sample_rate,channels,duration,nb_frames,nb_read_packets"
    ":stream_disposition=attached_pic"
    ":stream_side_data=rotation"
)


@dataclass(frozen=True)
class StreamInfo:
    index: int
    kind: str
    codec: str
    duration: float | None = None
    nb_frames: int | None = None
    nb_read_packets: int | None = None
    packet_start: float | None = None
    packet_end: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    rotation: int = 0
    sample_rate: int | None = None
    channels: int | None = None


@dataclass(frozen=True)
class ProbeObs:
    readable: bool
    error: str = ""
    format_duration: float | None = None
    video: StreamInfo | None = None
    audio: StreamInfo | None = None
    demuxer_messages: tuple[str, ...] = ()
    boxes: BoxWalk = field(default_factory=lambda: BoxWalk(is_isobmff=False))


_ADDRESS = re.compile(r" @ 0x[0-9a-fA-F]+")


def clean_log_line(line: str, path: Path) -> str:
    """Drop the file path and per-run memory addresses so reports are stable and leak nothing."""
    line = line.replace(str(path), path.name)
    return _ADDRESS.sub("", line).strip()


def _float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _fraction(value: object) -> float | None:
    if not isinstance(value, str) or "/" not in value:
        return None
    num, den = value.split("/", 1)
    n, d = _float(num), _float(den)
    if n is None or not d:
        return None
    return n / d


def parse_packets(csv_text: str) -> dict[int, tuple[float, float]]:
    """Map stream index -> (first pts, last pts + duration) from a packet CSV scan."""
    spans: dict[int, tuple[float, float]] = {}
    for line in csv_text.splitlines():
        parts = line.split(",")
        if len(parts) < 3:
            continue
        index, pts, dur = _int(parts[0]), _float(parts[1]), _float(parts[2])
        if index is None or pts is None:
            continue
        end = pts + (dur or 0.0)
        if index in spans:
            start, last = spans[index]
            spans[index] = (min(start, pts), max(last, end))
        else:
            spans[index] = (pts, end)
    return spans


def _stream(raw: dict, packets: dict[int, tuple[float, float]]) -> StreamInfo:
    index = int(raw["index"])
    span = packets.get(index)
    rotation = 0
    for side in raw.get("side_data_list") or []:
        if "rotation" in side:
            rotation = _int(side["rotation"]) or 0
    return StreamInfo(
        index=index,
        kind=raw.get("codec_type", ""),
        codec=raw.get("codec_name", ""),
        duration=_float(raw.get("duration")),
        nb_frames=_int(raw.get("nb_frames")),
        nb_read_packets=_int(raw.get("nb_read_packets")),
        packet_start=span[0] if span else None,
        packet_end=span[1] if span else None,
        width=_int(raw.get("width")),
        height=_int(raw.get("height")),
        fps=_fraction(raw.get("avg_frame_rate")),
        rotation=rotation,
        sample_rate=_int(raw.get("sample_rate")),
        channels=_int(raw.get("channels")),
    )


def build_probe(
    meta: dict,
    returncode: int,
    stderr: str,
    packets: dict[int, tuple[float, float]],
    boxes: BoxWalk,
) -> ProbeObs:
    messages = tuple(line.strip() for line in stderr.splitlines() if line.strip())[:20]
    streams = meta.get("streams") or []
    if returncode != 0 or not streams:
        error = " | ".join(messages[-3:]) if messages else "ffprobe found no streams"
        return ProbeObs(readable=False, error=error, demuxer_messages=messages, boxes=boxes)
    video = next(
        (s for s in streams
         if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return ProbeObs(
        readable=True,
        format_duration=_float((meta.get("format") or {}).get("duration")),
        video=_stream(video, packets) if video else None,
        audio=_stream(audio, packets) if audio else None,
        demuxer_messages=messages,
        boxes=boxes,
    )


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL
    )


def run_probe(path: Path) -> ProbeObs:
    # Absolute, so a name like "-intro.mp4" or "clip:1.mp4" is never read as an option/protocol.
    path = path.absolute()
    boxes = walk_boxes(path)
    meta_proc = _run(
        ["ffprobe", "-v", "error", "-count_packets", "-show_entries", _ENTRIES,
         "-of", "json", str(path)]
    )
    try:
        meta = json.loads(meta_proc.stdout or "{}")
    except json.JSONDecodeError:
        meta = {}
    stderr = "\n".join(clean_log_line(line, path) for line in meta_proc.stderr.splitlines())
    if meta_proc.returncode != 0 or not meta.get("streams"):
        return build_probe(meta, meta_proc.returncode, stderr, {}, boxes)
    packet_proc = _run(
        ["ffprobe", "-v", "error", "-show_entries", "packet=stream_index,pts_time,duration_time",
         "-of", "csv=p=0", str(path)]
    )
    return build_probe(
        meta, meta_proc.returncode, stderr, parse_packets(packet_proc.stdout), boxes
    )
