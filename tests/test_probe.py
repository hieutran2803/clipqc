import pytest

from clipqc.boxes import BoxWalk
from clipqc.probe import build_probe, clean_log_line, parse_packets, run_probe


def test_parse_packets_tracks_first_pts_and_last_end_per_stream():
    csv = "0,0.000000,0.033333\n1,-0.021333,0.021333,\n0,0.033333,0.033333\n0,N/A,0.03\n"
    spans = parse_packets(csv)
    assert spans[0] == pytest.approx((0.0, 0.066666))
    assert spans[1] == pytest.approx((-0.021333, 0.0))


def test_build_probe_skips_the_attached_cover_picture():
    meta = {
        "format": {"duration": "6.0"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "mjpeg",
             "disposition": {"attached_pic": 1}},
            {"index": 1, "codec_type": "video", "codec_name": "h264", "width": 720,
             "height": 1280, "avg_frame_rate": "30/1", "side_data_list": [{"rotation": -90}]},
            {"index": 2, "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
        ],
    }
    obs = build_probe(meta, 0, "", {1: (0.0, 6.0)}, BoxWalk(is_isobmff=True))
    assert obs.readable
    assert obs.video.index == 1
    assert obs.video.fps == 30.0
    assert obs.video.rotation == -90
    assert obs.video.packet_end == 6.0
    assert obs.audio.sample_rate == 48000


def test_build_probe_marks_non_zero_exit_unreadable_with_stderr_tail():
    obs = build_probe({}, 1, "a\nb\nmoov atom not found\nx.mp4: Invalid data\n", {},
                      BoxWalk(is_isobmff=True))
    assert obs.readable is False
    assert obs.error == "b | moov atom not found | x.mp4: Invalid data"


def test_clean_log_line_removes_path_and_addresses(tmp_path):
    path = tmp_path / "clip.mp4"
    line = f"[mov,mp4,m4a,3gp,3g2,mj2 @ 0xbd5408000] {path}: moov atom not found"
    assert clean_log_line(line, path) == "[mov,mp4,m4a,3gp,3g2,mj2] clip.mp4: moov atom not found"


def test_clean_clip(media):
    obs = run_probe(media / "clean.mp4")
    assert obs.readable
    assert obs.format_duration == pytest.approx(4.0, abs=0.05)
    assert (obs.video.width, obs.video.height) == (160, 284)
    assert obs.video.nb_read_packets == obs.video.nb_frames
    assert obs.video.packet_end == pytest.approx(4.0, abs=0.05)
    assert obs.audio.channels == 2


def test_truncated_clip_keeps_header_duration_but_loses_packets(media):
    obs = run_probe(media / "trunc.mp4")
    assert obs.readable
    assert obs.format_duration == pytest.approx(4.0, abs=0.05)
    assert obs.video.nb_read_packets < obs.video.nb_frames
    assert obs.video.packet_end < 3.5
    assert any("partial file" in m for m in obs.demuxer_messages)


def test_truncated_clip_with_moov_at_end_is_unreadable(media):
    obs = run_probe(media / "trunc_moovend.mp4")
    assert obs.readable is False
    assert "moov atom not found" in obs.error
    assert str(media) not in obs.error
    assert "0x" not in obs.error


def test_clip_without_audio(media):
    obs = run_probe(media / "noaudio.mp4")
    assert obs.video is not None
    assert obs.audio is None
