import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from fmike import audio, banana, install
from fmike.config import Config, repo_root
from fmike.errors import FmikeError


@dataclass(frozen=True, slots=True, kw_only=True)
class Check:
    name: str
    ok: bool
    detail: str
    fix: str


type Probe = tuple[str, Callable[[], str], str]


def evaluate(probes: Iterable[Probe]) -> list[Check]:
    results: list[Check] = []
    for name, probe, fix in probes:
        try:
            result = Check(name=name, ok=True, detail=probe(), fix="")
        except Exception as err:  # noqa: BLE001 - isolate every diagnostic from every other check
            result = Check(
                name=name,
                ok=False,
                detail=str(err),
                fix=err.fix if isinstance(err, FmikeError) else fix,
            )
        results.append(result)
    return results


def render(checks: Iterable[Check]) -> str:
    return "\n".join(
        f"{'✓' if check.ok else '✗'} {check.name}: {check.detail}"
        + (f"\n  fix: {check.fix}" if not check.ok else "")
        for check in checks
    )


def exit_code(checks: Iterable[Check]) -> int:
    return 0 if all(check.ok for check in checks) else 1


def run_checks(cfg: Config) -> list[Check]:
    def windows() -> str:
        audio.require_windows()
        return sys.platform

    def python() -> str:
        if sys.version_info[:2] != (3, 15):
            raise FmikeError(sys.version, fix="Run uv sync with Python 3.15.")
        return sys.version.split()[0]

    def installed() -> str:
        _ = banana.library()
        return "Banana remote DLL importable"

    def api() -> str:
        banana.ensure_running(cfg)
        return "Banana API answers"

    def playback() -> str:
        devices = audio.endpoints()
        return "; ".join(
            audio.resolve_playback(devices, mode, cfg).name for mode in audio.PlaybackMode
        )

    def capture() -> str:
        if not any(
            d.active and d.id.startswith("{0.0.1.") and d.name.startswith(cfg.devices.b1)
            for d in audio.endpoints()
        ):
            raise FmikeError(
                "B1 capture endpoint missing or inactive.",
                fix="Enable Voicemeeter Out B1 in Windows Sound; reboot after install.",
            )
        return cfg.devices.b1

    def startup() -> str:
        value = install.registered_startup()
        if value != install.startup_value(repo_root()) or not Path(value.strip('"')).is_file():
            raise FmikeError("Startup entry is stale.", fix="Run fmike install in this repository.")
        return value

    def shortcut() -> str:
        path = install.desired_shortcut().path
        if not path.is_file():
            raise FmikeError("Shortcut missing.", fix="Run fmike install.")
        return str(path)

    return evaluate(
        [
            ("Windows", windows, "Use Windows 11."),
            ("Python 3.15", python, "Run uv sync."),
            ("Banana installed", installed, banana.INSTALL_FIX),
            ("Banana API", api, banana.API_FIX),
            ("Microphone", lambda: audio.mic_status(cfg), "Connect and unmute your mic."),
            (
                "Playback devices",
                playback,
                "Connect devices or correct devices.solo / devices.party.",
            ),
            ("B1 capture", capture, "Enable Voicemeeter Out B1 in Sound settings."),
            ("Banana routing", lambda: banana.routing_status(cfg), "Run fmike install."),
            ("Startup", startup, "Run fmike install."),
            ("Shortcut", shortcut, "Run fmike install."),
        ]
    )
