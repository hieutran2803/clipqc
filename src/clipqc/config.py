"""clipqc.toml: flat keys, validated strictly so a typo is an error, not a silent default."""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

AUDIO_POLICIES = ("required", "optional", "forbidden")


class ConfigError(ValueError):
    """Raised for any unusable config; the CLI maps it to exit code 2."""


@dataclass(frozen=True)
class Config:
    audio: str = "required"
    loudness_target_lufs: float = -14.0
    loudness_tolerance_lu: float = 4.0
    duration_min_s: float = 1.0
    duration_max_s: float | None = None


_NUMERIC = {"loudness_target_lufs", "loudness_tolerance_lu", "duration_min_s", "duration_max_s"}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_config(data: dict) -> Config:
    known = {f.name for f in fields(Config)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(f"unknown config key(s): {', '.join(unknown)}")
    for key in _NUMERIC & set(data):
        if not _is_number(data[key]):
            raise ConfigError(f"{key} must be a number, got {data[key]!r}")
    if "audio" in data and data["audio"] not in AUDIO_POLICIES:
        raise ConfigError(f"audio must be one of {', '.join(AUDIO_POLICIES)}, got {data['audio']!r}")
    cfg = Config(**{k: (float(v) if k in _NUMERIC else v) for k, v in data.items()})
    if cfg.loudness_tolerance_lu <= 0:
        raise ConfigError("loudness_tolerance_lu must be > 0")
    if cfg.duration_min_s < 0:
        raise ConfigError("duration_min_s must be >= 0")
    if cfg.duration_max_s is not None and cfg.duration_max_s < cfg.duration_min_s:
        raise ConfigError("duration_max_s must be >= duration_min_s")
    return cfg


def load_config(path: Path | None) -> Config:
    if path is None:
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    return parse_config(data)
