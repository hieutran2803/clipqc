"""Hand-built observations for pure judge() tests. Defaults describe a clean 10 s clip."""
from dataclasses import replace

from clipqc.boxes import BoxWalk
from clipqc.decode import DecodeObs
from clipqc.probe import ProbeObs, StreamInfo

_DEFAULT = object()

VIDEO = StreamInfo(
    index=0, kind="video", codec="h264", duration=10.0, nb_frames=300, nb_read_packets=300,
    packet_start=0.0, packet_end=10.0, width=720, height=1280, fps=30.0,
)
AUDIO = StreamInfo(
    index=1, kind="audio", codec="aac", duration=10.0, nb_frames=469, nb_read_packets=469,
    packet_start=-0.021, packet_end=10.0, sample_rate=48000, channels=2,
)
FASTSTART = BoxWalk(is_isobmff=True, order=("ftyp", "moov", "mdat"))


def video(**changes) -> StreamInfo:
    return replace(VIDEO, **changes)


def audio(**changes) -> StreamInfo:
    return replace(AUDIO, **changes)


def probe(video=_DEFAULT, audio=_DEFAULT, **changes) -> ProbeObs:
    base = ProbeObs(
        readable=True, format_duration=10.0,
        video=VIDEO if video is _DEFAULT else video,
        audio=AUDIO if audio is _DEFAULT else audio,
        boxes=FASTSTART,
    )
    return replace(base, **changes)


def decode(**changes) -> DecodeObs:
    base = DecodeObs(
        audio_decoded=True, loudness_summaries=1, astats_blocks=1, integrated_lufs=-14.0,
        true_peak_dbtp=-3.0, sample_peak_dbfs=-3.5, flat_factor=0.0, peak_count=2.0,
    )
    return replace(base, **changes)
