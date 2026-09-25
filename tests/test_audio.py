import math

import pytest
from factories import audio, decode, probe

from clipqc.config import Config
from clipqc.detectors.audio import judge_audio
from clipqc.model import Severity, Status

CFG = Config()


def codes(result):
    return [f.code for f in result.findings]


def test_clean_audio_passes():
    assert judge_audio(probe(), decode(), CFG).status is Status.PASS


def test_unreadable_container_is_skipped():
    assert judge_audio(probe(readable=False), None, CFG).status is Status.SKIPPED


@pytest.mark.parametrize("policy, status", [("required", Status.FAIL), ("optional", Status.PASS),
                                            ("forbidden", Status.PASS)])
def test_missing_audio_follows_the_policy(policy, status):
    assert judge_audio(probe(audio=None), decode(), Config(audio=policy)).status is status


def test_forbidden_audio_that_exists_fails():
    result = judge_audio(probe(), decode(), Config(audio="forbidden"))
    assert codes(result) == ["audio.unexpected"]


def test_no_decode_pass_is_inconclusive():
    assert judge_audio(probe(), None, CFG).status is Status.INCONCLUSIVE


def test_more_than_one_summary_is_inconclusive_not_pass():
    result = judge_audio(probe(), decode(loudness_summaries=2, astats_blocks=2), CFG)
    assert result.status is Status.INCONCLUSIVE
    assert "got 2 and 2" in result.reason


def test_digital_silence_fails():
    d = decode(integrated_lufs=-70.0, sample_peak_dbfs=-math.inf, true_peak_dbtp=-math.inf,
               flat_factor=-math.inf, peak_count=960000.0)
    result = judge_audio(probe(), d, CFG)
    assert codes(result) == ["audio.silent"]


def test_near_silent_fails_when_audio_is_required():
    d = decode(integrated_lufs=-50.2, sample_peak_dbfs=-38.1, true_peak_dbtp=-38.1)
    assert codes(judge_audio(probe(), d, CFG)) == ["audio.near_silent"]


def test_optional_audio_skips_the_silence_checks_and_loudness():
    d = decode(integrated_lufs=-50.2, sample_peak_dbfs=-38.1, true_peak_dbtp=-38.1)
    assert judge_audio(probe(), d, Config(audio="optional")).status is Status.PASS


def test_short_clip_is_not_called_silent_from_the_minus_70_lufs_artifact():
    p = probe(format_duration=0.5, audio=audio(packet_start=0.0, packet_end=0.5))
    d = decode(integrated_lufs=-70.0, sample_peak_dbfs=-10.5)
    assert judge_audio(p, d, CFG).status is Status.PASS


@pytest.mark.parametrize(
    "count, flat, severity",
    [(48000 * 10 * 2e-3, 0.0, Severity.FAIL),
     (48000 * 10 * 1e-4, 0.0, Severity.WARN),
     (2.0, 15.0, Severity.FAIL),
     (2.0, 0.0, None)],
)
def test_clipping_grades(count, flat, severity):
    p = probe(audio=audio(packet_start=0.0, packet_end=10.0))
    d = decode(sample_peak_dbfs=0.0, peak_count=count, flat_factor=flat, true_peak_dbtp=-1.5)
    found = [f for f in judge_audio(p, d, CFG).findings if f.code == "audio.clipping"]
    assert [f.severity for f in found] == ([severity] if severity else [])


def test_full_scale_count_is_ignored_below_the_clip_level():
    d = decode(sample_peak_dbfs=-3.0, peak_count=960000.0)
    assert judge_audio(probe(), d, CFG).status is Status.PASS


@pytest.mark.parametrize("tp, severity", [(0.5, Severity.FAIL), (-0.5, Severity.WARN),
                                          (-1.5, None), (-math.inf, None)])
def test_true_peak_grades(tp, severity):
    found = [f for f in judge_audio(probe(), decode(true_peak_dbtp=tp), CFG).findings
             if f.code == "audio.true_peak"]
    assert [f.severity for f in found] == ([severity] if severity else [])


def test_loudness_off_target_is_only_a_warning():
    result = judge_audio(probe(), decode(integrated_lufs=-20.0), CFG)
    assert result.status is Status.WARN
    assert codes(result) == ["audio.loudness"]


def test_loudness_within_tolerance_passes():
    assert judge_audio(probe(), decode(integrated_lufs=-16.0), CFG).status is Status.PASS


def test_loudness_is_not_judged_on_clips_under_three_seconds():
    p = probe(format_duration=2.0, audio=audio(packet_start=0.0, packet_end=2.0))
    assert judge_audio(p, decode(integrated_lufs=-25.0), CFG).status is Status.PASS
