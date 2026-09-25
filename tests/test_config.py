import pytest

from clipqc.config import Config, ConfigError, load_config, parse_config


def test_defaults_match_the_spec():
    cfg = Config()
    assert cfg.audio == "required"
    assert cfg.loudness_target_lufs == -14.0
    assert cfg.loudness_tolerance_lu == 4.0
    assert cfg.duration_min_s == 1.0
    assert cfg.duration_max_s is None


def test_no_path_means_defaults():
    assert load_config(None) == Config()


def test_loads_flat_toml(tmp_path):
    p = tmp_path / "clipqc.toml"
    p.write_text('audio = "optional"\nduration_min_s = 5\nduration_max_s = 30.5\n')
    cfg = load_config(p)
    assert cfg.audio == "optional"
    assert cfg.duration_min_s == 5.0
    assert cfg.duration_max_s == 30.5


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"audoi": "optional"}, "unknown config key"),
        ({"audio": "maybe"}, "audio must be one of"),
        ({"duration_min_s": "5"}, "must be a number"),
        ({"duration_min_s": True}, "must be a number"),
        ({"loudness_tolerance_lu": 0}, "must be > 0"),
        ({"duration_min_s": 10, "duration_max_s": 5}, "duration_max_s must be >="),
    ],
)
def test_rejects_bad_values(data, fragment):
    with pytest.raises(ConfigError, match=fragment):
        parse_config(data)


def test_unreadable_toml_is_a_config_error(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("audio = \n")
    with pytest.raises(ConfigError, match="cannot read config"):
        load_config(p)


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="cannot read config"):
        load_config(tmp_path / "nope.toml")
