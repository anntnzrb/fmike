import importlib
import logging
import subprocess
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Protocol, Self, cast

from fmike.audio import require_windows
from fmike.config import Config, Preset
from fmike.errors import BananaNotInstalledError, BananaUnavailableError

log = logging.getLogger(__name__)
INSTALL_FIX = "winget install -e --id VB-Audio.Voicemeeter.Banana; then reboot Windows."
API_FIX = "Start Voicemeeter Banana; reboot Windows if Banana was just installed."


class Device(Protocol):
    name: str
    wdm: str


class Strip(Protocol):
    device: Device
    label: str
    A1: bool
    B1: bool


class Bus(Protocol):
    device: Device


type Settings = dict[str, dict[str, float | int | str | bool | dict[str, float]]]


class Remote(Protocol):
    strip: list[Strip]
    bus: list[Bus]

    def apply(self, settings: Settings) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *args: object) -> None: ...


class Library(Protocol):
    def api(self, kind: str, *, timeout: float) -> Remote: ...


def library() -> Library:
    require_windows()
    try:
        # Import itself checks installation; importing eagerly would break doctor and uninstall.
        return cast("Library", cast("object", importlib.import_module("voicemeeterlib")))
    except ImportError as err:
        raise BananaNotInstalledError(str(err), fix=INSTALL_FIX) from err
    except OSError as err:
        raise BananaNotInstalledError(str(err), fix=INSTALL_FIX) from err
    except Exception as err:
        if type(err).__name__ == "InstallError":
            raise BananaNotInstalledError(str(err), fix=INSTALL_FIX) from err
        raise


@contextmanager
def connection() -> Generator[Remote]:
    lib = library()
    try:
        with lib.api("banana", timeout=2.0) as vm:
            yield vm
    except Exception as err:
        if type(err).__name__ == "VMError":
            raise BananaUnavailableError(str(err), fix=API_FIX) from err
        raise


def ensure_running(cfg: Config) -> None:
    _ = library()
    if not cfg.banana_exe.is_file():
        raise BananaNotInstalledError(
            f"Banana executable missing: {cfg.banana_exe}", fix=INSTALL_FIX
        )
    try:
        tasks = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {cfg.banana_exe.name}", "/NH"],
            check=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if cfg.banana_exe.name.casefold() not in tasks.stdout.casefold():
            log.info("starting %s", cfg.banana_exe)
            _ = subprocess.Popen([str(cfg.banana_exe)])
    except (OSError, subprocess.SubprocessError) as err:
        raise BananaUnavailableError(str(err), fix=API_FIX) from err
    deadline = time.monotonic() + 30.0
    while True:
        try:
            with connection():
                return
        except BananaUnavailableError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1.0)


def apply_preset(vm: Remote, preset: Preset) -> None:
    vm.apply(
        {
            "strip-0": {
                "gain": preset.gain,
                "limit": preset.limit,
                "comp": {"knob": preset.compression},
                "label": preset.label,
            }
        }
    )


def reconcile(cfg: Config) -> None:
    ensure_running(cfg)
    with connection() as vm:
        if vm.strip[0].device.name != cfg.devices.mic:
            vm.strip[0].device.wdm = cfg.devices.mic
        if vm.bus[0].device.name != cfg.devices.clock:
            vm.bus[0].device.wdm = cfg.devices.clock
        vm.apply({"strip-0": {"A1": False, "B1": True, "mute": False}})
        apply_preset(vm, cfg.clean)
    log.info("reconciled mic -> B1 only, clean preset")


def read_funny(cfg: Config) -> bool:
    with connection() as vm:
        return vm.strip[0].label == cfg.funny.label


def set_funny(cfg: Config, *, funny: bool | None) -> bool:
    ensure_running(cfg)
    with connection() as vm:
        enabled = vm.strip[0].label != cfg.funny.label if funny is None else funny
        apply_preset(vm, cfg.funny if enabled else cfg.clean)
    import winsound  # noqa: PLC0415 - Windows-only boundary

    winsound.Beep(1200 if enabled else 500, 120)
    return enabled


def routing_status(cfg: Config) -> str:
    with connection() as vm:
        strip = vm.strip[0]
        if strip.device.name != cfg.devices.mic or not strip.B1 or strip.A1:
            raise BananaUnavailableError(
                "Banana strip 0 routing differs from config.",
                fix="Run fmike install to reconcile mic routing to B1 only.",
            )
    return "strip 0: configured mic, B1 on, A1 off"
