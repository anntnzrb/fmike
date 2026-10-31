# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pycaw/comtypes expose generated COM interfaces without usable type information.
import sys
import warnings
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Protocol, cast

from fmike.config import Config
from fmike.errors import DeviceNotFoundError, FmikeError, NotWindowsError


class Policy(Protocol):
    def SetEndpointVisibility(self, device_id: str, visible: bool, /) -> None: ...  # noqa: N802, FBT001 - COM signature


class PlaybackMode(StrEnum):
    SOLO = auto()
    PARTY = auto()


@dataclass(frozen=True, slots=True, kw_only=True)
class Endpoint:
    id: str
    name: str
    active: bool


def require_windows() -> None:
    if sys.platform != "win32":
        raise NotWindowsError("fmike requires Windows.", fix="Run on Windows 11.")


def filter_comtypes_warning() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r"You are running 'comtypes' on Python 3\.15, where the behavior of enum types.*",
        category=FutureWarning,
        module=r"(?:comtypes(?:\..*)?|fmike\.audio)",
    )


@contextmanager
def session() -> Generator[None]:
    require_windows()
    filter_comtypes_warning()
    import comtypes  # noqa: PLC0415 - Windows-only COM boundary

    comtypes.CoInitialize()
    try:
        yield
    except (OSError, comtypes.COMError) as err:
        raise FmikeError(
            f"Windows audio operation failed: {err}",
            fix="Reconnect your audio devices and restart Windows Audio or reboot.",
        ) from err
    finally:
        comtypes.CoUninitialize()


def endpoints() -> list[Endpoint]:
    with session():
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

        return [
            Endpoint(id=d.id, name=d.FriendlyName, active=d.state.value == 1)
            for d in AudioUtilities.GetAllDevices()
        ]


def resolve_playback(devices: Iterable[Endpoint], mode: PlaybackMode, cfg: Config) -> Endpoint:
    prefix = cfg.devices.solo if mode == PlaybackMode.SOLO else cfg.devices.party
    for device in devices:
        if device.id.startswith("{0.0.0.") and device.active and device.name.startswith(prefix):
            return device
    raise DeviceNotFoundError(
        f"Playback device {prefix!r} not found or not active.",
        fix=f"Connect and enable {prefix!r} in Windows Sound settings, or edit devices.{mode}.",
    )


def set_playback(mode: PlaybackMode, cfg: Config) -> str:
    device = resolve_playback(endpoints(), mode, cfg)
    with session():
        from pycaw.constants import ERole  # noqa: PLC0415
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

        AudioUtilities.SetDefaultDevice(
            device.id, roles=[ERole.eConsole, ERole.eMultimedia, ERole.eCommunications]
        )
    return f"{mode}: default playback -> {device.name}"


def current_playback(cfg: Config) -> PlaybackMode | None:
    with session():
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

        device = AudioUtilities.GetSpeakers()
        if device is None:
            raise DeviceNotFoundError(
                "No default playback device.", fix="Enable a playback device."
            )
        name: str = device.FriendlyName
    return next(
        (
            mode
            for mode, prefix in (
                (PlaybackMode.SOLO, cfg.devices.solo),
                (PlaybackMode.PARTY, cfg.devices.party),
            )
            if name.startswith(prefix)
        ),
        None,
    )


def mic_status(cfg: Config) -> str:
    with session():
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

        for device in AudioUtilities.GetAllDevices():
            if device.id.startswith("{0.0.1.") and device.FriendlyName == cfg.devices.mic:
                if device.state.value == 1 and not device.EndpointVolume.GetMute():
                    return f"{cfg.devices.mic}: active, unmuted"
                break
    raise DeviceNotFoundError(
        f"Microphone {cfg.devices.mic!r} missing, inactive, or muted.",
        fix="Connect, enable, and unmute the mic; correct devices.mic in config.toml.",
    )


def hide_junk(cfg: Config) -> None:
    with session():
        import comtypes  # noqa: PLC0415
        from pycaw.api.policyconfig import IPolicyConfig  # noqa: PLC0415
        from pycaw.constants import CLSID_CPolicyConfigClient  # noqa: PLC0415
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

        policy = cast(
            "Policy",
            cast(
                "object",
                comtypes.CoCreateInstance(
                    CLSID_CPolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL
                ),
            ),
        )
        for device in AudioUtilities.GetAllDevices():
            if device.state.value == 1 and not device.FriendlyName.startswith(cfg.devices.keep):
                policy.SetEndpointVisibility(device.id, False)
