import pytest
from factories import decode, probe, video, audio

from clipqc.boxes import BoxWalk
from clipqc.config import Config
from clipqc.detectors.frame import judge_frame
from clipqc.model import Severity, Status

CFG = Config()


def codes(result):
    return [f.code for f in result.findings]


def test_clean_clip_passes():
    result = judge_frame(probe(), decode(), CFG)
    assert result.status is Status.PASS
    assert result.findings == ()
    assert result.coverage == 1.0


def test_unreadable_container_fails_with_zero_coverage():
    result = judge_frame(probe(readable=False, error="moov atom not found"), None, CFG)
    assert result.status is Status.FAIL
    assert codes(result) == ["frame.unreadable_container"]
    assert "moov atom not found" in result.findings[0].message
    assert result.coverage == 0.0


def test_missing_video_stream_fails():
    result = judge_frame(probe(video=None), decode(), CFG)
    assert codes(result) == ["frame.no_video"]


def test_truncated_file_reports_the_break_and_coverage():
    p = probe(video=video(nb_read_packets=150, packet_end=5.0),
              audio=audio(nb_read_packets=230, packet_end=4.9))
    result = judge_frame(p, decode(), CFG)
    assert result.status is Status.FAIL
    finding = result.findings[0]
    assert finding.code == "frame.truncated"
    assert finding.t_start == pytest.approx(4.9)
    assert result.coverage == pytest.approx(0.49)


def test_packet_count_short_of_nb_frames_alone_is_not_truncation():
    # PCM audio in MOV reports samples as nb_frames; stream-copy trims drop leading packets.
    p = probe(audio=audio(codec="pcm_s16le", nb_frames=480000, nb_read_packets=469),
              video=video(nb_frames=300, nb_read_packets=255))
    assert judge_frame(p, decode(), CFG).status is Status.PASS


def test_truncated_when_media_ends_well_before_the_header_duration():
    p = probe(video=video(nb_frames=None, packet_end=6.0), audio=audio(nb_frames=None,
                                                                       packet_end=6.0))
    assert "frame.truncated" in codes(judge_frame(p, decode(), CFG))


def test_truncated_when_a_box_overruns_the_file():
    p = probe(boxes=BoxWalk(True, ("ftyp", "moov", "mdat"), "box 'mdat' claims 9 bytes"))
    assert "frame.truncated" in codes(judge_frame(p, decode(), CFG))


def test_truncation_suppresses_the_decoder_errors_and_av_gap_it_causes():
    p = probe(video=video(packet_end=5.0), audio=audio(packet_end=4.2))
    d = decode(decoder_error_count=3, decoder_errors=("[h264] Invalid NAL unit size",))
    assert codes(judge_frame(p, d, CFG)) == ["frame.truncated"]


def test_decoder_errors_fail_an_intact_container():
    d = decode(decoder_error_count=31, decoder_errors=("[h264] Invalid NAL unit size",))
    result = judge_frame(probe(), d, CFG)
    assert codes(result) == ["frame.decode_error"]
    assert result.findings[0].evidence["count"] == 31


@pytest.mark.parametrize("end, expected", [(0.5, ["frame.duration"]), (1.0, [])])
def test_duration_floor(end, expected):
    p = probe(format_duration=end, video=video(packet_end=end), audio=audio(packet_end=end))
    assert codes(judge_frame(p, decode(), CFG)) == expected


def test_duration_ceiling_from_config():
    result = judge_frame(probe(), decode(), Config(duration_max_s=8.0))
    assert codes(result) == ["frame.duration"]


@pytest.mark.parametrize(
    "a_end, v_end, severity",
    [(10.2, 10.0, None), (10.5, 10.0, Severity.WARN), (11.5, 10.0, Severity.FAIL)],
)
def test_av_mismatch_thresholds(a_end, v_end, severity):
    p = probe(format_duration=max(a_end, v_end), video=video(packet_end=v_end),
              audio=audio(packet_end=a_end))
    found = [f for f in judge_frame(p, decode(), CFG).findings if f.code == "frame.av_mismatch"]
    assert [f.severity for f in found] == ([severity] if severity else [])


def test_av_mismatch_allows_two_percent_on_long_clips():
    p = probe(format_duration=101.5, video=video(packet_end=100.0), audio=audio(packet_end=101.5))
    found = [f for f in judge_frame(p, decode(), CFG).findings if f.code == "frame.av_mismatch"]
    assert [f.severity for f in found] == [Severity.WARN]


def test_moov_after_mdat_is_a_warning():
    p = probe(boxes=BoxWalk(True, ("ftyp", "free", "mdat", "moov")))
    result = judge_frame(p, decode(), CFG)
    assert result.status is Status.WARN
    assert codes(result) == ["frame.faststart"]


def test_black_interval_fails_with_times():
    result = judge_frame(probe(), decode(black=((2.0, 3.0),)), CFG)
    assert result.status is Status.FAIL
    f = result.findings[0]
    assert (f.code, f.t_start, f.t_end) == ("frame.black", 2.0, 3.0)


def test_frozen_interval_is_a_warning():
    result = judge_frame(probe(), decode(freeze=((1.0, 4.0),)), CFG)
    assert result.status is Status.WARN
    assert codes(result) == ["frame.frozen"]


def test_freeze_inside_a_black_interval_is_not_reported_twice():
    d = decode(black=((2.0, 5.0),), freeze=((2.05, 5.03),))
    assert codes(judge_frame(probe(), d, CFG)) == ["frame.black"]


def test_freeze_without_an_end_runs_to_the_end_of_the_video():
    f = judge_frame(probe(), decode(freeze=((7.0, None),)), CFG).findings[0]
    assert f.t_end == 10.0


def test_mid_file_parameter_change_is_a_warning():
    d = decode(params_changed=("Reconfiguring filter graph because video parameters changed",))
    assert codes(judge_frame(probe(), d, CFG)) == ["frame.params_changed"]


def test_missing_decode_pass_is_inconclusive_unless_something_already_failed():
    ok = judge_frame(probe(), None, CFG)
    assert ok.status is Status.INCONCLUSIVE
    assert ok.reason
    overrun = BoxWalk(True, ("ftyp", "moov", "mdat"), "box 'mdat' claims 9 bytes")
    truncated = judge_frame(probe(boxes=overrun), None, CFG)
    assert truncated.status is Status.FAIL
