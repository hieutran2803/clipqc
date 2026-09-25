from factories import probe, video

from clipqc.batch import judge_batch


def portrait():
    return probe(video=video(width=720, height=1280, fps=30.0))


def test_fewer_than_three_clips_is_not_a_batch():
    assert judge_batch({"a": portrait(), "b": probe(video=video(width=1280, height=720))}) == {}


def test_flags_the_clip_that_differs_from_the_majority():
    probes = {"a": portrait(), "b": portrait(), "c": portrait(),
              "d": probe(video=video(width=1280, height=720))}
    found = judge_batch(probes)
    assert list(found) == ["d"]
    assert found["d"][0].code == "frame.batch_mismatch"
    assert found["d"][0].evidence == {"attribute": "resolution", "value": "1280x720",
                                      "majority": "720x1280"}


def test_rotation_metadata_counts_as_displayed_resolution_but_is_flagged_itself():
    probes = {"a": portrait(), "b": portrait(), "c": portrait(),
              "d": probe(video=video(width=1280, height=720, rotation=90))}
    found = judge_batch(probes)
    assert [f.evidence["attribute"] for f in found["d"]] == ["rotation"]


def test_no_majority_means_no_finding():
    probes = {"a": portrait(), "b": portrait(),
              "c": probe(video=video(fps=25.0)), "d": probe(video=video(fps=25.0))}
    assert judge_batch(probes) == {}


def test_unreadable_clips_are_left_out():
    probes = {"a": portrait(), "b": portrait(), "c": portrait(), "x": probe(readable=False)}
    assert judge_batch(probes) == {}
