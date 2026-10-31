# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingTypeStubs=false
# WScript.Shell is a dynamically generated COM interface.
import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fmike import audio, banana
from fmike.config import Config, repo_root
from fmike.errors import FmikeError

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "fmike"


@dataclass(frozen=True, slots=True, kw_only=True)
class Shortcut:
    path: Path
    target: Path
    arguments: str
    working_directory: Path
    hotkey: str


def startup_value(root: Path) -> str:
    return f'"{root / ".venv/Scripts/fmike-tray.exe"}"'


def shortcut_spec(root: Path, appdata: Path) -> Shortcut:
    return Shortcut(
        path=appdata / "Microsoft/Windows/Start Menu/Programs/fmike toggle.lnk",
        target=root / ".venv/Scripts/pythonw.exe",
        arguments="-m fmike toggle",
        working_directory=root,
        hotkey="CTRL+ALT+F",
    )


def desired_shortcut() -> Shortcut:
    return shortcut_spec(repo_root(), Path(os.environ["APPDATA"]))


def registered_startup() -> str:
    audio.require_windows()
    import winreg  # noqa: PLC0415 - Windows boundary

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        result = cast("tuple[object, int]", winreg.QueryValueEx(key, RUN_NAME))
    return str(result[0])


def register() -> None:
    audio.require_windows()
    import winreg  # noqa: PLC0415

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_value(repo_root()))
        spec = desired_shortcut()
        spec.path.parent.mkdir(parents=True, exist_ok=True)
        with audio.session():
            from comtypes.client import CreateObject  # noqa: PLC0415

            # WScript avoids PowerShell quoting/encoding and writes native .lnk hotkeys directly.
            shell = CreateObject("WScript.Shell", dynamic=True)
            shortcut = shell.CreateShortcut(str(spec.path))
            shortcut.TargetPath = str(spec.target)
            shortcut.Arguments = spec.arguments
            shortcut.WorkingDirectory = str(spec.working_directory)
            shortcut.Hotkey = spec.hotkey
            shortcut.Save()
    except OSError as err:
        raise FmikeError(
            str(err), fix="Check your user profile permissions, then re-run install."
        ) from err


def install(cfg: Config) -> None:
    audio.require_windows()
    import winreg  # noqa: PLC0415 - Windows-only legacy install migration

    # Pre-publication names; remove this migration once existing installs have moved.
    legacy_run_names = ("Funny Mic Tray", "Voicemeeter Banana")
    legacy_shortcut_names = ("Funny Mic Toggle.lnk",)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            for name in legacy_run_names:
                with suppress(FileNotFoundError):
                    winreg.DeleteValue(key, name)
        programs = desired_shortcut().path.parent
        for name in legacy_shortcut_names:
            (programs / name).unlink(missing_ok=True)
    except OSError as err:
        raise FmikeError(
            str(err), fix="Check your user profile permissions, then re-run fmike install."
        ) from err

    audio.hide_junk(cfg)
    register()
    banana.reconcile(cfg)
    _ = audio.set_playback(audio.PlaybackMode.SOLO, cfg)


def uninstall() -> None:
    audio.require_windows()
    import winreg  # noqa: PLC0415

    try:
        with (
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key,
            suppress(FileNotFoundError),
        ):
            winreg.DeleteValue(key, RUN_NAME)
        desired_shortcut().path.unlink(missing_ok=True)
    except FileNotFoundError:
        desired_shortcut().path.unlink(missing_ok=True)
    except OSError as err:
        raise FmikeError(
            str(err), fix="Check your user profile permissions and retry uninstall."
        ) from err
