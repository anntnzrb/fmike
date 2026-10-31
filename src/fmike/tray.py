# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingTypeStubs=false, reportUnknownLambdaType=false, reportAny=false
# pystray callbacks and generated Win32/COM APIs are untyped boundary objects.
import ctypes
import logging
import os
import threading
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

import pystray
from PIL import Image, ImageDraw, ImageFont

from fmike import audio, banana, doctor
from fmike.config import Config, load_config
from fmike.errors import FmikeError

log = logging.getLogger(__name__)
ERROR_ALREADY_EXISTS = 183


class TrayIcon(Protocol):
    icon: Image.Image
    title: str
    visible: bool

    def update_menu(self) -> None: ...
    def notify(self, message: str, title: str) -> None: ...
    def stop(self) -> None: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class TrayState:
    funny: bool | None = None
    mode: audio.PlaybackMode | None = None


def icon_style(state: TrayState) -> tuple[tuple[int, int, int], str]:
    match state.funny:
        case None:
            color = (110, 110, 110)
        case True:
            color = (220, 40, 40)
        case False:
            color = (40, 170, 70)
    letter = "?" if state.mode is None else "S" if state.mode == audio.PlaybackMode.SOLO else "P"
    return color, letter


def tray_image(state: TrayState) -> Image.Image:
    color, letter = icon_style(state)
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, 62, 62), fill=color)
    draw.text((32, 32), letter, fill="white", font=ImageFont.load_default(size=40), anchor="mm")
    return image


def log_directory() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "fmike"


def run(cfg: Config | None, initial_error: FmikeError | None = None) -> None:

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, r"Local\fmike-tray")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _ = kernel.CloseHandle(mutex)
        log.info("tray already running")
        return
    state = TrayState()
    stop = threading.Event()
    lock = threading.Lock()
    problem = initial_error is not None

    def refresh(icon: TrayIcon) -> None:
        nonlocal state
        if cfg is None or problem:
            icon.icon = tray_image(TrayState())
            icon.title = "fmike: problem — open Diagnostics"
            return
        with lock:
            state = TrayState(funny=banana.read_funny(cfg), mode=audio.current_playback(cfg))
        icon.icon = tray_image(state)
        icon.title = (
            f"fmike: {'FUNNY' if state.funny else 'clean'} | {state.mode or 'other device'}"
        )
        icon.update_menu()

    def notify(icon: TrayIcon, err: Exception) -> None:
        log.error("tray operation failed: %s", err)
        icon.notify(err.fix if isinstance(err, FmikeError) else str(err), "fmike")

    def toggle(icon: TrayIcon, _item: pystray.MenuItem) -> None:
        nonlocal problem
        try:
            if cfg is None:
                raise initial_error or load_error()
            with lock:
                _ = banana.set_funny(cfg, funny=None)
            problem = False
            refresh(icon)
        except Exception as err:  # noqa: BLE001 - GUI callback must remain alive
            notify(icon, err)

    def switch(icon: TrayIcon, mode: audio.PlaybackMode) -> None:
        try:
            if cfg is None:
                raise initial_error or load_error()
            with lock:
                _ = audio.set_playback(mode, cfg)
            refresh(icon)
        except Exception as err:  # noqa: BLE001 - GUI callback boundary
            notify(icon, err)

    def diagnostics(icon: TrayIcon, _item: pystray.MenuItem) -> None:
        try:
            current = load_config()
            report = doctor.render(doctor.run_checks(current))
        except Exception as err:  # noqa: BLE001 - diagnostics must work even with invalid config
            report = (
                f"error: {err}\nfix: {err.fix if isinstance(err, FmikeError) else 'Check log.'}"
            )
        try:
            path = log_directory() / "doctor.txt"
            _ = path.write_text(report + "\n", encoding="utf-8")
            os.startfile(path)  # noqa: S606 - open our own generated local diagnostic text
        except OSError as err:
            notify(icon, err)

    def quit_tray(icon: TrayIcon, _item: pystray.MenuItem) -> None:
        stop.set()
        icon.stop()

    def poll(icon: TrayIcon) -> None:
        nonlocal problem
        icon.visible = True
        try:
            if initial_error is not None:
                raise initial_error
            if cfg is not None:
                with lock:
                    banana.reconcile(cfg)
                    _ = audio.set_playback(audio.PlaybackMode.SOLO, cfg)
                log.info("boot reconcile complete")
        except Exception as err:  # noqa: BLE001 - retain grey tray and diagnostics on boot failure
            problem = True
            notify(icon, err)
        while not stop.is_set():
            try:
                refresh(icon)
            except Exception as err:
                log.exception("poll failed")
                icon.icon = tray_image(TrayState())
                icon.title = "fmike: problem — open Diagnostics"
                log.debug("poll error: %s", err)
            if stop.wait(cfg.poll_seconds if cfg is not None else 1.5):
                break

    menu = pystray.Menu(
        pystray.MenuItem(
            "Funny mic", toggle, checked=lambda _item: bool(state.funny), default=True
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Solo (monitor speakers)",
            lambda icon, _item: switch(icon, audio.PlaybackMode.SOLO),
            checked=lambda _item: state.mode == audio.PlaybackMode.SOLO,
            radio=True,
        ),
        pystray.MenuItem(
            "Party (Razer headset)",
            lambda icon, _item: switch(icon, audio.PlaybackMode.PARTY),
            checked=lambda _item: state.mode == audio.PlaybackMode.PARTY,
            radio=True,
        ),
        pystray.MenuItem("Diagnostics…", diagnostics),
        pystray.MenuItem("Quit", quit_tray),
    )
    icon = pystray.Icon("fmike", tray_image(state), "fmike: starting", menu)
    try:
        icon.run(setup=poll)
    finally:
        stop.set()
        _ = kernel.CloseHandle(mutex)


def load_error() -> FmikeError:
    return FmikeError("Configuration unavailable.", fix="Correct config.toml and restart the tray.")


def main() -> None:
    audio.require_windows()
    folder = log_directory()
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        folder / "fmike.log", maxBytes=256 * 1024, backupCount=1, encoding="utf-8"
    )
    logging.basicConfig(
        handlers=[handler],
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("voicemeeterlib").setLevel(logging.WARNING)
    log.info("tray starting")
    try:
        cfg = load_config()
    except FmikeError as err:
        run(None, err)
    else:
        run(cfg)
