from pathlib import Path

import pytest

from fmike.config import load_config
from fmike.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]


def test_committed_config() -> None:
    cfg = load_config(ROOT / "config.toml")
    assert cfg.devices.mic == "Microphone (Razer USB Sound Card)"
    assert cfg.funny.gain == 12.0
    assert cfg.funny.color == (0.5, 1.0)
    assert cfg.clean.eq == ()
    assert cfg.poll_seconds == 1.5


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ('mic = "Microphone (Razer USB Sound Card)"', "", "devices.mic"),
        ("poll_seconds = 1.5", 'poll_seconds = "fast"', "poll_seconds"),
        ("poll_seconds = 1.5", "poll_seconds = 1.5\nextra = 1", "extra"),
        ("    [3150, 18, 2.0],", "    [3150, 19, 2.0],", "presets.funny.eq"),
        ("    [3150, 18, 2.0],", "    [3150, 18],", "presets.funny.eq"),
        ("color = [0.5, 1.0]", "color = [0.5, 2.0]", "presets.funny.color"),
        ("gain = 12.0", "gain = 13.0", "presets.funny.gain"),
        ("eq = []", "eq = [" + "[100, 0, 1], " * 7 + "]", "presets.clean.eq"),
    ],
)
def test_invalid_config(tmp_path: Path, old: str, new: str, key: str) -> None:
    path = tmp_path / "config.toml"
    _ = path.write_text(
        (ROOT / "config.toml").read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
    )
    with pytest.raises(ConfigError) as caught:
        _ = load_config(path)
    assert key in str(caught.value)
    assert key in caught.value.fix
