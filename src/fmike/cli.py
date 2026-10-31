import argparse
import sys
from io import TextIOWrapper

from fmike import audio, banana, doctor, install, tray
from fmike.config import load_config
from fmike.errors import FmikeError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Voicemeeter Banana funny mic and playback control"
    )
    _ = parser.add_argument(
        "command",
        nargs="?",
        default="tray",
        choices=[
            "tray",
            "on",
            "off",
            "toggle",
            "status",
            "solo",
            "party",
            "doctor",
            "install",
            "uninstall",
        ],
    )

    class Arguments(argparse.Namespace):
        command: str = "tray"

    command = parser.parse_args(namespace=Arguments()).command
    try:
        if command == "tray":
            tray.main()
            return 0
        if command == "uninstall":
            install.uninstall()
            print("Removed startup and hotkey. Hidden devices were left unchanged.")
            print(
                "Re-show devices: Sound control panel > Playback/Recording > Show Disabled Devices."
            )
            print("Right-click a hidden device and choose Enable.")
            return 0
        cfg = load_config()
        match command:
            case "doctor" | "install":
                if command == "install":
                    install.install(cfg)
                checks = doctor.run_checks(cfg)
                # Windows redirected consoles can still use a legacy code page.
                if isinstance(sys.stdout, TextIOWrapper):
                    sys.stdout.reconfigure(encoding="utf-8")
                print(doctor.render(checks))
                return doctor.exit_code(checks)
            case "solo" | "party":
                print(audio.set_playback(audio.PlaybackMode(command), cfg))
            case "status":
                print("funny mic ON" if banana.read_funny(cfg) else "funny mic OFF")
            case "on" | "off" | "toggle":
                enabled = banana.set_funny(
                    cfg, funny=None if command == "toggle" else command == "on"
                )
                print("funny mic ON" if enabled else "funny mic OFF")
            case _:
                parser.error(f"Unknown command: {command}")
    except FmikeError as err:
        print(f"error: {err}", file=sys.stderr)
        print(f"fix: {err.fix}", file=sys.stderr)
        return 2
    return 0
