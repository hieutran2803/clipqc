import math

import pytest

from clipqc.decode import build_decode_cmd, parse_decode_log, run_decode
from clipqc.probe import run_probe

# Trimmed from real ffmpeg 8.1.2 output (-loglevel level+info).
SUMMARY = """\
[Parsed_ebur128_0 @ 0x795059b00] [info] Summary:

  Integrated loudness:
    I:         -28.3 LUFS
    Threshold: -38.3 LUFS

  True peak:
    Peak:      -19.5 dBFS
[Parsed_astats_2 @ 0x795059c80] [info] Overall
[Parsed_astats_2 @ 0x795059c80] [info] Peak level dB: -19.532234
[Parsed_astats_2 @ 0x795059c80] [info] Flat factor: 4.436975
[Parsed_astats_2 @ 0x795059c80] [info] Peak count: 3.000000
"""


def test_parses_black_loudness_and_astats():
    log = "[Parsed_blackdetect_1 @ 0x7950] [info] black_start:2 black_end:3.033333 " \
          "black_duration:1.033333\n" + SUMMARY
    obs = parse_decode_log(log, 0, audio_decoded=True)
    assert obs.black == ((2.0, 3.033333),)
    assert obs.loudness_summaries == 1
    assert obs.astats_blocks == 1
    assert obs.integrated_lufs == -28.3
    assert obs.true_peak_dbtp == -19.5
    assert obs.sample_peak_dbfs == pytest.approx(-19.532234)
    assert obs.flat_factor == pytest.approx(4.436975)
    assert obs.peak_count == 3.0


def test_parses_minus_inf_from_digital_silence():
    log = SUMMARY.replace("-28.3 LUFS", "-70.0 LUFS").replace("-19.5 dBFS", " -inf dBFS") \
        .replace("Peak level dB: -19.532234", "Peak level dB: -inf")
    obs = parse_decode_log(log, 0, audio_decoded=True)
    assert obs.integrated_lufs == -70.0
    assert obs.true_peak_dbtp == -math.inf
    assert obs.sample_peak_dbfs == -math.inf


def test_pairs_freeze_events_and_leaves_an_eof_freeze_open():
    log = (
        "[Parsed_freezedetect_2 @ 0x1] [info] lavfi.freezedetect.freeze_start: 1\n"
        "[Parsed_freezedetect_2 @ 0x1] [info] lavfi.freezedetect.freeze_duration: 3.03\n"
        "[Parsed_freezedetect_2 @ 0x1] [info] lavfi.freezedetect.freeze_end: 4.033333\n"
        "[Parsed_freezedetect_2 @ 0x1] [info] lavfi.freezedetect.freeze_start: 9.5\n"
    )
    obs = parse_decode_log(log, 0, audio_decoded=False)
    assert obs.freeze == ((1.0, 4.033333), (9.5, None))


def test_counts_decoder_errors_but_not_wrappers_demuxers_or_swscaler():
    log = (
        "[h264 @ 0x1] [error] Invalid NAL unit size (1182 > 165).\n"
        "[h264 @ 0x1] [error] Invalid NAL unit size (1182 > 165).\n"
        "[aac @ 0x2] [error] Reserved bit set.\n"
        "[vist#0:0/h264 @ 0x3] [dec:h264 @ 0x4] [error] Decoding error: Invalid data\n"
        "[in#0/mov,mp4,m4a,3gp,3g2,mj2 @ 0x5] [error] stream 1, offset 0x33dd4: partial file\n"
        "[swscaler @ 0x6] [swscaler @ 0x7] [warning] No accelerated colorspace conversion\n"
        "[aac @ 0x2] [warning] Sample rate index does not match\n"
    )
    obs = parse_decode_log(log, 0, audio_decoded=True)
    assert obs.decoder_error_count == 3
    assert obs.decoder_errors == (
        "[h264] Invalid NAL unit size (1182 > 165).",
        "[aac] Reserved bit set.",
    )


def test_parses_lines_already_stripped_of_addresses():
    log = "[Parsed_blackdetect_1] [info] black_start:2 black_end:3 black_duration:1\n" \
          "[h264] [error] Invalid NAL unit size (1 > 2).\n"
    obs = parse_decode_log(log, 0, audio_decoded=False)
    assert obs.black == ((2.0, 3.0),)
    assert obs.decoder_error_count == 1


def test_records_filter_graph_reconfiguration():
    log = "[vf#0:0 @ 0x1] [info] Reconfiguring filter graph because video parameters " \
          "changed to yuv420p(tv, smpte170m), 320x568\n"
    obs = parse_decode_log(log, 0, audio_decoded=False)
    assert len(obs.params_changed) == 1


def test_counts_every_loudness_summary():
    obs = parse_decode_log(SUMMARY + SUMMARY, 0, audio_decoded=True)
    assert obs.loudness_summaries == 2
    assert obs.astats_blocks == 2


def test_cmd_maps_exact_stream_indexes_and_skips_missing_streams(tmp_path):
    cmd = build_decode_cmd(tmp_path / "a.mp4", 1, None)
    assert cmd[cmd.index("-map") + 1] == "0:1"
    assert "-af" not in cmd
    assert "-nostdin" in cmd


def test_black_clip(media):
    obs = run_decode(media / "black.mp4", run_probe(media / "black.mp4"))
    assert len(obs.black) == 1
    start, end = obs.black[0]
    assert start == pytest.approx(1.0, abs=0.05)
    assert end == pytest.approx(2.0, abs=0.1)


def test_frozen_clip(media):
    obs = run_decode(media / "frozen.mp4", run_probe(media / "frozen.mp4"))
    assert len(obs.freeze) == 1
    assert obs.freeze[0][0] == pytest.approx(1.0, abs=0.1)


def test_clean_clip_has_one_summary_and_no_errors(media):
    obs = run_decode(media / "clean.mp4", run_probe(media / "clean.mp4"))
    assert obs.black == () and obs.freeze == ()
    assert obs.decoder_error_count == 0
    assert obs.loudness_summaries == 1 and obs.astats_blocks == 1
    assert obs.integrated_lufs == pytest.approx(-14.3, abs=1.0)


def test_silent_clip(media):
    obs = run_decode(media / "silent.mp4", run_probe(media / "silent.mp4"))
    assert obs.sample_peak_dbfs == -math.inf
    assert obs.integrated_lufs <= -60


def test_clipped_clip(media):
    obs = run_decode(media / "clipped.mp4", run_probe(media / "clipped.mp4"))
    assert obs.sample_peak_dbfs >= -0.1
    assert obs.true_peak_dbtp > 0


def test_corrupt_payload_produces_decoder_errors(media):
    obs = run_decode(media / "corrupt.mp4", run_probe(media / "corrupt.mp4"))
    assert obs.decoder_error_count >= 1


def test_mid_file_colorspace_change_keeps_one_audio_summary(media):
    obs = run_decode(media / "mixcs.mp4", run_probe(media / "mixcs.mp4"))
    assert len(obs.params_changed) >= 1
    assert obs.loudness_summaries == 1
    assert obs.astats_blocks == 1


def test_clip_without_audio_decodes_video_only(media):
    obs = run_decode(media / "noaudio.mp4", run_probe(media / "noaudio.mp4"))
    assert obs.audio_decoded is False
    assert obs.loudness_summaries == 0
