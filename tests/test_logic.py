from pathlib import Path

import pytest

from fmike.audio import Endpoint, PlaybackMode, resolve_playback
from fmike.banana import preset_script
from fmike.config import load_config
from fmike.doctor import Check, evaluate, exit_code, render
from fmike.errors import DeviceNotFoundError
from fmike.install import RUN_NAME, shortcut_spec, startup_value
from fmike.tray import TrayState, icon_style, tray_image

ROOT = Path(__file__).resolve().parents[1]


def test_playback_uses_active_render_device() -> None:
    cfg = load_config(ROOT / "config.toml")
    devices = [
        Endpoint(id="{0.0.1.capture", name="VG245 (capture)", active=True),
        Endpoint(id="{0.0.0.disabled", name="VG245 (disabled)", active=False),
        Endpoint(id="{0.0.0.monitor", name="VG245 (NVIDIA)", active=True),
    ]
    assert resolve_playback(devices, PlaybackMode.SOLO, cfg).id == "{0.0.0.monitor"
    with pytest.raises(DeviceNotFoundError, match="Speakers"):
        _ = resolve_playback(devices, PlaybackMode.PARTY, cfg)


def test_startup_paths_and_quoting(tmp_path: Path) -> None:
    root = tmp_path / "a repo with spaces"
    assert RUN_NAME == "fmike"
    assert startup_value(root) == f'"{root / ".venv/Scripts/fmike-tray.exe"}"'
    spec = shortcut_spec(root, tmp_path)
    assert spec.target == root / ".venv/Scripts/pythonw.exe"
    assert spec.arguments == "-m fmike toggle"
    assert spec.working_directory == root
    assert spec.hotkey == "CTRL+ALT+F"
    assert spec.path == tmp_path / "Microsoft/Windows/Start Menu/Programs/fmike toggle.lnk"


def test_doctor_report_and_status() -> None:
    good = Check(name="Windows", ok=True, detail="Windows 11", fix="")
    bad = Check(name="Mic", ok=False, detail="Missing", fix="Connect microphone.")
    assert "✓" in render([good])
    assert exit_code([good]) == 0
    assert "✗" in render([good, bad])
    assert "fix: Connect microphone." in render([good, bad])
    assert exit_code([good, bad]) == 1


def test_check_failure_does_not_skip_later_checks() -> None:
    def broken() -> str:
        msg = "unavailable device"
        raise OSError(msg)

    checks = evaluate([("broken", broken, "Reconnect."), ("next", lambda: "ready", "")])
    assert len(checks) == 2
    assert not checks[0].ok
    assert "unavailable device" in checks[0].detail
    assert checks[1].ok


def test_preset_script_drives_b1_eq_and_clears_unused_cells() -> None:
    cfg = load_config(ROOT / "config.toml")
    funny = dict(line.split("=", 1) for line in preset_script(cfg.funny).split(";"))
    assert funny["Strip[0].Gain"] == "12"
    assert funny["Strip[0].Color_y"] == "1"
    assert funny["Strip[0].Label"] == '"mic FUNNY"'
    assert funny["Bus[3].EQ.on"] == "1"
    assert funny["Bus[3].EQ.channel[0].cell[3].gain"] == "18"
    clean = dict(line.split("=", 1) for line in preset_script(cfg.clean).split(";"))
    assert clean["Bus[3].EQ.on"] == "0"
    assert all(clean[f"Bus[3].EQ.channel[0].cell[{i}].on"] == "0" for i in range(6))
    assert clean["Strip[0].Color_x"] == "0"


@pytest.mark.parametrize(
    ("funny", "mode", "color", "letter"),
    [
        (None, None, (110, 110, 110), "?"),
        (False, PlaybackMode.SOLO, (40, 170, 70), "S"),
        (True, PlaybackMode.PARTY, (220, 40, 40), "P"),
    ],
)
def test_tray_state_image(
    funny: bool | None, mode: PlaybackMode | None, color: tuple[int, int, int], letter: str
) -> None:
    state = TrayState(funny=funny, mode=mode)
    assert icon_style(state) == (color, letter)
    image = tray_image(state)
    assert image.size == (64, 64)
    assert image.getpixel((32, 8)) == (*color, 255)
