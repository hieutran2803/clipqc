"""Container and picture checks. judge_frame() is pure: observations in, verdict out."""
from __future__ import annotations

from clipqc.config import Config
from clipqc.decode import DecodeObs
from clipqc.model import DetectorResult, Finding, Severity, Status, status_from_findings
from clipqc.probe import ProbeObs

NAME = "frame"
AV_WARN_S = 0.25
AV_FAIL_S = 1.0
AV_FAIL_FRACTION = 0.02
TRUNCATION_MIN_GAP_S = 0.5
BLACK_OVERLAP_SLACK_S = 0.1


def _stream_ends(probe: ProbeObs) -> list[float]:
    return [s.packet_end for s in (probe.video, probe.audio) if s and s.packet_end is not None]


def _truncation(probe: ProbeObs) -> Finding | None:
    # Packet count vs nb_frames is NOT a signal on its own: PCM audio in MOV reports samples
    # as frames, and stream-copy trims drop packets before the edit list on healthy files.
    reasons = []
    ends = _stream_ends(probe)
    header = probe.format_duration
    if ends and header:
        fps = probe.video.fps if probe.video and probe.video.fps else 30.0
        if max(ends) < header - max(TRUNCATION_MIN_GAP_S, 2.0 / fps):
            reasons.append(f"media ends at {max(ends):.2f}s but the header says {header:.2f}s")
    if probe.boxes.overrun:
        reasons.append(probe.boxes.overrun)
    if not reasons:
        return None
    t_break = min(ends) if ends else None
    where = f" at {t_break:.2f}s" if t_break is not None else ""
    return Finding(
        "frame.truncated", Severity.FAIL, f"file is truncated{where}: " + "; ".join(reasons),
        t_start=t_break, evidence={"reasons": reasons},
    )


def _inside_black(start: float, end: float, black: tuple[tuple[float, float], ...]) -> bool:
    return any(b0 - BLACK_OVERLAP_SLACK_S <= start and end <= b1 + BLACK_OVERLAP_SLACK_S
               for b0, b1 in black)


def judge_frame(probe: ProbeObs, decode: DecodeObs | None, cfg: Config) -> DetectorResult:
    if not probe.readable:
        return DetectorResult(
            NAME, Status.FAIL,
            (Finding("frame.unreadable_container", Severity.FAIL,
                     f"container cannot be read: {probe.error}"),),
            coverage=0.0,
        )
    if probe.video is None:
        return DetectorResult(
            NAME, Status.FAIL, (Finding("frame.no_video", Severity.FAIL, "no video stream"),),
            coverage=0.0,
        )

    findings: list[Finding] = []
    truncated = _truncation(probe)
    if truncated:
        findings.append(truncated)

    ends = _stream_ends(probe)
    length = max(ends) if ends else (probe.format_duration or 0.0)
    if length < cfg.duration_min_s:
        findings.append(Finding(
            "frame.duration", Severity.FAIL,
            f"clip is {length:.2f}s, shorter than the {cfg.duration_min_s:.2f}s minimum",
            evidence={"duration_s": length}))
    elif cfg.duration_max_s is not None and length > cfg.duration_max_s:
        findings.append(Finding(
            "frame.duration", Severity.FAIL,
            f"clip is {length:.2f}s, longer than the {cfg.duration_max_s:.2f}s maximum",
            evidence={"duration_s": length}))

    v_end = probe.video.packet_end
    a_end = probe.audio.packet_end if probe.audio else None
    if v_end is not None and a_end is not None and truncated is None:
        diff = a_end - v_end
        fail_at = max(AV_FAIL_S, AV_FAIL_FRACTION * max(v_end, a_end))
        severity = (Severity.FAIL if abs(diff) > fail_at
                    else Severity.WARN if abs(diff) > AV_WARN_S else None)
        if severity:
            findings.append(Finding(
                "frame.av_mismatch", severity,
                f"video ends at {v_end:.2f}s, audio at {a_end:.2f}s ({diff:+.2f}s)",
                t_start=min(v_end, a_end), t_end=max(v_end, a_end),
                evidence={"video_end_s": v_end, "audio_end_s": a_end}))

    boxes = probe.boxes
    if boxes.is_isobmff and {"moov", "mdat"} <= set(boxes.order) \
            and boxes.order.index("moov") > boxes.order.index("mdat"):
        findings.append(Finding(
            "frame.faststart", Severity.WARN,
            "moov box is after mdat, so web players must fetch the whole file before playing "
            "(remux: ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4)",
            evidence={"box_order": list(boxes.order)}))

    coverage = 1.0
    if truncated and truncated.t_start is not None and probe.format_duration:
        coverage = max(0.0, min(1.0, truncated.t_start / probe.format_duration))

    if decode is None:
        status = Status.FAIL if status_from_findings(findings) is Status.FAIL \
            else Status.INCONCLUSIVE
        return DetectorResult(NAME, status, tuple(findings), coverage,
                              reason="decode pass did not run")

    if decode.decoder_error_count and truncated is None:
        findings.append(Finding(
            "frame.decode_error", Severity.FAIL,
            f"{decode.decoder_error_count} decoder error(s), e.g. {decode.decoder_errors[0]}",
            evidence={"count": decode.decoder_error_count,
                      "examples": list(decode.decoder_errors)}))

    for start, end in decode.black:
        findings.append(Finding(
            "frame.black", Severity.FAIL, f"black frames {start:.2f}s-{end:.2f}s",
            t_start=start, t_end=end))

    video_end = v_end if v_end is not None else length
    for start, end in decode.freeze:
        stop = end if end is not None else video_end
        if _inside_black(start, stop, decode.black):
            continue
        findings.append(Finding(
            "frame.frozen", Severity.WARN, f"frozen picture {start:.2f}s-{stop:.2f}s",
            t_start=start, t_end=stop))

    if decode.params_changed:
        findings.append(Finding(
            "frame.params_changed", Severity.WARN,
            f"video parameters change mid-file ({len(decode.params_changed)}x); "
            "black/frozen intervals spanning a change may be split",
            evidence={"changes": list(decode.params_changed[:3])}))

    return DetectorResult(NAME, status_from_findings(findings), tuple(findings), coverage)
