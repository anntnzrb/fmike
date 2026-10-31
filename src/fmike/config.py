import math
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fmike.errors import ConfigError


@dataclass(frozen=True, slots=True, kw_only=True)
class Devices:
    mic: str
    clock: str
    solo: str
    party: str
    b1: str
    input: str

    @property
    def keep(self) -> tuple[str, ...]:
        return (self.mic, self.clock, self.solo, self.party, self.b1, self.input)


@dataclass(frozen=True, slots=True, kw_only=True)
class Preset:
    gain: float
    limit: int
    compression: float
    label: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    devices: Devices
    clean: Preset
    funny: Preset
    banana_exe: Path
    poll_seconds: float


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def invalid(key: str, reason: str) -> ConfigError:
    return ConfigError(f"Config key {key}: {reason}", fix=f"Correct {key} in config.toml.")


def table(value: object, keys: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise invalid(name, "expected a table")
    data = cast("dict[str, object]", value)
    if missing := keys - data.keys():
        raise invalid(f"{name}{min(missing)}", "missing required key")
    if extra := data.keys() - keys:
        raise invalid(f"{name}{min(extra)}", "unknown key")
    return data


def text(value: object, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid(key, "expected a non-empty string")
    return value


def number(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise invalid(key, "expected a number")
    if not math.isfinite(value):
        raise invalid(key, "expected a finite number")
    return float(value)


def preset(value: object, name: str) -> Preset:
    data = table(value, {"gain", "limit", "compression", "label"}, f"presets.{name}.")
    limit = data["limit"]
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise invalid(f"presets.{name}.limit", "expected an integer")
    return Preset(
        gain=number(data["gain"], f"presets.{name}.gain"),
        limit=limit,
        compression=number(data["compression"], f"presets.{name}.compression"),
        label=text(data["label"], f"presets.{name}.label"),
    )


def load_config(path: Path | None = None) -> Config:
    path = path or Path(os.environ.get("FMIKE_CONFIG", repo_root() / "config.toml"))
    try:
        with path.open("rb") as stream:
            raw: object = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise ConfigError(
            f"Cannot read config {path}: {err}",
            fix="Correct FMIKE_CONFIG or restore the repository config.toml.",
        ) from err
    data = table(raw, {"devices", "presets", "banana_exe", "poll_seconds"}, "")
    devices = table(data["devices"], {"mic", "clock", "solo", "party", "b1", "input"}, "devices.")
    presets = table(data["presets"], {"clean", "funny"}, "presets.")
    poll = number(data["poll_seconds"], "poll_seconds")
    if poll <= 0:
        raise invalid("poll_seconds", "must be positive")
    return Config(
        devices=Devices(**{key: text(value, f"devices.{key}") for key, value in devices.items()}),
        clean=preset(presets["clean"], "clean"),
        funny=preset(presets["funny"], "funny"),
        banana_exe=Path(text(data["banana_exe"], "banana_exe")),
        poll_seconds=poll,
    )
