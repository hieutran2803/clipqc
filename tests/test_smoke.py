import clipqc


def test_version_is_set():
    assert clipqc.__version__.startswith("0.1.")
