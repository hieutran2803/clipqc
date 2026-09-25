"""One decoding pass per clip. Video and audio run as SEPARATE simple filtergraphs
(-vf / -af), so a mid-file video parameter change re-initialises only the video
filters and the audio summaries stay single."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from clipqc.probe import ProbeObs, clean_log_line

VIDEO_CHAIN = (
    "scale=180:-2:flags=fast_bilinear,"
    "blackdetect=d=0.5:pix_th=0.10,"
    "freezedetect=n=-60dB:d=2"
)
AUDIO_CHAIN = (
    "ebur128=peak=true:framelog=quiet,"
    "aformat=sample_fmts=s16,"
    "astats=measure_perchannel=none:measure_overall=Peak_level+Flat_factor+Peak_count"
)

_LINE = re.compile(
    r"^\[(?P<ctx>[^\]\s]+)(?: @ [^\]]+)?\](?: \[[^\]]+\])*? "
    r"\[(?P<level>trace|debug|verbose|info|warning|error|fatal|panic)\] (?P<msg>.*)$"
)
_DECODER_CTX = re.compile(r"[a-z0-9_]+")
_OUR_FILTERS = ("scale", "blackdetect", "freezedetect", "ebur128", "aformat", "astats")
_NOT_DECODERS = {"swscaler", "swresample", *_OUR_FILTERS}
_BLACK = re.compile(r"black_start:\s*(-?[\d.]+)\s+black_end:\s*(-?[\d.]+)")
_FREEZE_START = re.compile(r"freeze_start:\s*(-?[\d.]+)")
_FREEZE_END = re.compile(r"freeze_end:\s*(-?[\d.]+)")
_I = re.compile(r"^\s*I:\s+(\S+)\s+LUFS")
_TP = re.compile(r"^\s*Peak:\s+(\S+)\s+dBFS")
_ASTAT = re.compile(r"^(Peak level dB|Flat factor|Peak count):\s*(\S+)")
_ADDRESS = re.compile(r" @ 0x[0-9a-fA-F]+")


@dataclass(frozen=True)
class DecodeObs:
    returncode: int = 0
    black: tuple[tuple[float, float], ...] = ()
    freeze: tuple[tuple[float, float | None], ...] = ()
    params_changed: tuple[str, ...] = ()
    decoder_errors: tuple[str, ...] = ()
    decoder_error_count: int = 0
    audio_decoded: bool = False
    loudness_summaries: int = 0
    astats_blocks: int = 0
    integrated_lufs: float | None = None
    true_peak_dbtp: float | None = None
    sample_peak_dbfs: float | None = None
    flat_factor: float | None = None
    peak_count: float | None = None


def _is_filter(ctx: str, name: str) -> bool:
    """ffmpeg >= 8.1 logs filters as "Parsed_<name>_<n>"; 6.1 and 8.0 log plain "<name>"."""
    return ctx == name or ctx.startswith(f"Parsed_{name}_")


def _num(text: str) -> float | None:
    try:
        return float(text)  # accepts "-inf", "inf", "nan"
    except ValueError:
        return None


def build_decode_cmd(path: Path, video_index: int | None, audio_index: int | None) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-loglevel", "level+info",
           "-i", str(path)]
    if video_index is not None:
        cmd += ["-map", f"0:{video_index}", "-vf", VIDEO_CHAIN]
    if audio_index is not None:
        cmd += ["-map", f"0:{audio_index}", "-af", AUDIO_CHAIN]
    return cmd + ["-f", "null", "-"]


def parse_decode_log(text: str, returncode: int, audio_decoded: bool) -> DecodeObs:
    black: list[tuple[float, float]] = []
    freeze: list[list[float | None]] = []
    changed: list[str] = []
    errors: list[str] = []
    error_count = 0
    summaries = blocks = 0
    in_summary = False
    lufs = tp = peak = flat = count = None

    for raw in text.splitlines():
        m = _LINE.match(raw)
        ctx, level, body = (m["ctx"], m["level"], m["msg"]) if m else ("", "", raw)
        if m and not _is_filter(ctx, "ebur128"):
            in_summary = False

        if level in ("error", "fatal", "panic") and _DECODER_CTX.fullmatch(ctx) \
                and ctx not in _NOT_DECODERS:
            error_count += 1
            msg = _ADDRESS.sub("", f"[{ctx}] {body}")
            if msg not in errors and len(errors) < 5:
                errors.append(msg)
        elif "Reconfiguring filter graph" in body:
            changed.append(body)
        elif _is_filter(ctx, "blackdetect") and (b := _BLACK.search(body)):
            black.append((float(b[1]), float(b[2])))
        elif _is_filter(ctx, "freezedetect") and (s := _FREEZE_START.search(body)):
            freeze.append([float(s[1]), None])
        elif _is_filter(ctx, "freezedetect") and (e := _FREEZE_END.search(body)):
            open_ = [f for f in freeze if f[1] is None]
            if open_:
                open_[-1][1] = float(e[1])
        elif _is_filter(ctx, "ebur128") and body.strip() == "Summary:":
            summaries += 1
            in_summary = True
        elif in_summary and (i := _I.match(body)):
            lufs = _num(i[1])
        elif in_summary and (t := _TP.match(body)):
            tp = _num(t[1])
        elif _is_filter(ctx, "astats") and body.strip() == "Overall":
            blocks += 1
        elif _is_filter(ctx, "astats") and (a := _ASTAT.match(body.strip())):
            value = _num(a[2])
            if a[1] == "Peak level dB":
                peak = value
            elif a[1] == "Flat factor":
                flat = value
            else:
                count = value

    return DecodeObs(
        returncode=returncode,
        black=tuple(black),
        freeze=tuple((f[0], f[1]) for f in freeze),
        params_changed=tuple(changed),
        decoder_errors=tuple(errors),
        decoder_error_count=error_count,
        audio_decoded=audio_decoded,
        loudness_summaries=summaries,
        astats_blocks=blocks,
        integrated_lufs=lufs,
        true_peak_dbtp=tp,
        sample_peak_dbfs=peak,
        flat_factor=flat,
        peak_count=count,
    )


def run_decode(path: Path, probe: ProbeObs) -> DecodeObs:
    path = path.absolute()  # never let a file name be read as an ffmpeg option
    video = probe.video.index if probe.video else None
    audio = probe.audio.index if probe.audio else None
    if video is None and audio is None:
        return DecodeObs()
    proc = subprocess.run(
        build_decode_cmd(path, video, audio), capture_output=True, text=True,
        errors="replace", stdin=subprocess.DEVNULL,
    )
    log = "\n".join(clean_log_line(line, path) for line in proc.stderr.splitlines())
    return parse_decode_log(log, proc.returncode, audio_decoded=audio is not None)
