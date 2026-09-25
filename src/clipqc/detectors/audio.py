"""Audio checks. judge_audio() is pure: observations in, verdict out."""
from __future__ import annotations

import math

from clipqc.config import Config
from clipqc.decode import DecodeObs
from clipqc.model import DetectorResult, Finding, Severity, Status, status_from_findings
from clipqc.probe import ProbeObs

NAME = "audio"
SILENT_DB = -60.0
NEAR_SILENT_LUFS = -40.0
MIN_SILENCE_JUDGE_S = 1.0     # ebur128 reports -70 LUFS for anything under one 400 ms block
MIN_LOUDNESS_S = 3.0
CLIP_PEAK_DBFS = -0.1
CLIP_FAIL_RATIO = 1e-3
CLIP_WARN_RATIO = 1e-5
FLAT_FACTOR_FAIL = 10.0
TRUE_PEAK_WARN_DBTP = -1.0
TRUE_PEAK_FAIL_DBTP = 0.0


def _finite(x: float | None) -> bool:
    return x is not None and math.isfinite(x)


def judge_audio(probe: ProbeObs, decode: DecodeObs | None, cfg: Config) -> DetectorResult:
    if not probe.readable:
        return DetectorResult(NAME, Status.SKIPPED, reason="container cannot be read")
    stream = probe.audio
    if stream is None:
        if cfg.audio == "required":
            return DetectorResult(NAME, Status.FAIL,
                                  (Finding("audio.missing", Severity.FAIL, "no audio stream"),))
        return DetectorResult(NAME, Status.PASS)
    if cfg.audio == "forbidden":
        return DetectorResult(NAME, Status.FAIL, (Finding(
            "audio.unexpected", Severity.FAIL,
            "audio stream present but the config says audio = forbidden"),))
    if decode is None or not decode.audio_decoded:
        return DetectorResult(NAME, Status.INCONCLUSIVE, reason="decode pass did not run")
    if decode.loudness_summaries != 1 or decode.astats_blocks != 1:
        return DetectorResult(NAME, Status.INCONCLUSIVE, reason=(
            f"expected one loudness summary and one astats block, got "
            f"{decode.loudness_summaries} and {decode.astats_blocks}"))

    if stream.packet_start is not None and stream.packet_end is not None:
        duration = stream.packet_end - stream.packet_start
    else:
        duration = stream.duration or probe.format_duration or 0.0
    lufs, peak = decode.integrated_lufs, decode.sample_peak_dbfs
    findings: list[Finding] = []

    if cfg.audio == "required":
        if peak is not None and peak <= SILENT_DB:
            findings.append(Finding("audio.silent", Severity.FAIL,
                                    f"audio is silent (sample peak {peak} dBFS)"))
        elif duration >= MIN_SILENCE_JUDGE_S and lufs is not None and lufs <= SILENT_DB:
            findings.append(Finding("audio.silent", Severity.FAIL,
                                    f"audio is silent ({lufs} LUFS integrated)"))
        elif duration >= MIN_SILENCE_JUDGE_S and lufs is not None and lufs < NEAR_SILENT_LUFS:
            findings.append(Finding(
                "audio.near_silent", Severity.FAIL,
                f"audio is nearly silent ({lufs:.1f} LUFS integrated, below {NEAR_SILENT_LUFS})",
                evidence={"integrated_lufs": lufs}))

    if _finite(peak) and peak >= CLIP_PEAK_DBFS and duration > 0 and stream.sample_rate:
        ratio = (decode.peak_count or 0.0) / (duration * stream.sample_rate)
        flat = decode.flat_factor if _finite(decode.flat_factor) else 0.0
        severity = (Severity.FAIL if ratio >= CLIP_FAIL_RATIO or flat > FLAT_FACTOR_FAIL
                    else Severity.WARN if ratio >= CLIP_WARN_RATIO else None)
        if severity:
            findings.append(Finding(
                "audio.clipping", severity,
                f"{ratio:.3%} of samples at full scale (flat factor {flat:.1f})",
                evidence={"clipped_ratio": ratio, "flat_factor": flat}))

    tp = decode.true_peak_dbtp
    if _finite(tp) and tp > TRUE_PEAK_WARN_DBTP:
        severity = Severity.FAIL if tp > TRUE_PEAK_FAIL_DBTP else Severity.WARN
        findings.append(Finding(
            "audio.true_peak", severity,
            f"true peak {tp:+.1f} dBTP (limit {TRUE_PEAK_WARN_DBTP:.0f} dBTP)",
            evidence={"true_peak_dbtp": tp}))

    if duration >= MIN_LOUDNESS_S and _finite(lufs) and lufs >= NEAR_SILENT_LUFS \
            and abs(lufs - cfg.loudness_target_lufs) > cfg.loudness_tolerance_lu:
        findings.append(Finding(
            "audio.loudness", Severity.WARN,
            f"integrated loudness {lufs:.1f} LUFS is {lufs - cfg.loudness_target_lufs:+.1f} LU "
            f"from the {cfg.loudness_target_lufs:.0f} LUFS target",
            evidence={"integrated_lufs": lufs}))

    return DetectorResult(NAME, status_from_findings(findings), tuple(findings))
