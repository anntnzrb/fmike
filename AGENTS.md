# Repository Guidelines

## Project Overview
`fmike` is a Windows-only tray app and CLI. It toggles a "funny mic" preset (heavy gain, compression and limiter) on a Voicemeeter Banana strip, with the mic routed to B1. It also switches the default Windows playback device between **solo** (monitor) and **party** (speakers). A global hotkey `CTRL+ALT+F` runs `fmike toggle`. License: AGPL-3.0-or-later (`COPYING`).

## Architecture & Data Flow
- **Inputs**: tray menu clicks, the `CTRL+ALT+F` Start Menu shortcut (`.venv/Scripts/pythonw.exe -m fmike toggle`), CLI subcommands, and a tray poll thread that runs every `poll_seconds`.
- **External systems are the source of truth.** `TrayState(funny, mode)` in `tray.py` is derived from the Voicemeeter strip label and the current default audio endpoint. Never keep state that the next poll can't rebuild.
- **Concurrency**: plain threads with a `threading.Lock` around shared state and Banana/COM calls. There is no asyncio. COM threads must call `CoInitialize`/`CoUninitialize`.
- **Outputs**: Banana parameter writes, `winsound.Beep`, default-endpoint switches through `pycaw`/`IPolicyConfig`, tray icon and notifications, and a log at `%LOCALAPPDATA%/fmike/fmike.log` (`RotatingFileHandler`).
- **Single instance**: the tray takes the named mutex `Local\fmike-tray`.

Module roles (`src/fmike/`):
| Module | Role |
|---|---|
| `cli.py` | argparse subcommands: `tray on off toggle status solo party doctor install uninstall`. Maps `FmikeError` to exit code 2. |
| `tray.py` | pystray app, 64×64 PIL icon (`tray_image`, `icon_style`), poll loop, logging setup |
| `banana.py` | `voicemeeterlib` client: `ensure_running`, applies presets, reconciles routing (mic→B1 only) |
| `audio.py` | Core Audio COM: endpoint listing, `resolve_playback` (pure), setting the default device, hiding devices, `require_windows()` |
| `config.py` | Strict `tomllib` loader that returns frozen, slotted dataclasses (`Config`, `Devices`, `Preset`) |
| `doctor.py` | Diagnostic probes: `evaluate` → `render` / `exit_code` (0 all ok, 1 otherwise) |
| `install.py` | HKCU `Run` value `fmike`, the `fmike toggle.lnk` hotkey shortcut, legacy-name cleanup |
| `errors.py` | `FmikeError(message, *, fix=...)` and its subclasses |

`src/funnymic/` and the root `__pycache__/funnymic.*.pyc` are leftovers from the old package name. They hold no source; don't add code there.

## Key Directories
- `src/fmike/`: the only real package (uv_build src layout).
- `tests/`: pytest suite covering pure logic only.
- `.github/workflows/ci.yml`: CI, runs on `windows-latest` only.

## Development Commands
```powershell
uv sync --locked                 # create .venv (Python 3.15)
uv run ruff check                # lint (select = ALL)
uv run ruff format --check       # format check; drop --check to apply
uv run basedpyright              # type check (strict "all" mode)
uv run pytest                    # tests
uv run fmike doctor              # live environment diagnostics
uv run fmike status | toggle | solo | party
uv run fmike install             # re-run after moving the repo (registry and shortcut store absolute paths)
powershell -ExecutionPolicy Bypass -File install.ps1   # full bootstrap: winget uv + Banana, uv sync, fmike install
```
CI runs exactly: `uv sync --locked`, `ruff check`, `ruff format --check`, `basedpyright`, `pytest`. Run all of them before you call work done.

## Code Conventions & Common Patterns
- **Errors**: raise an `FmikeError` subclass and always pass a keyword-only `fix=` with an actionable remediation the user can act on. Wrap `OSError`/`comtypes.COMError` with `raise FmikeError(..., fix=...) from err`. The CLI prints `error:` and `fix:` to stderr. The tray and doctor show `err.fix`.
- **Keep pure logic separate from Windows calls.** Put decisions in functions that take plain data (`resolve_playback(Iterable[Endpoint], ...)`, `evaluate([(name, probe, fix), ...])`, `startup_value(path)`, `shortcut_spec(...)`). Keep COM, registry and Banana I/O in thin wrappers. This split is what keeps tests hardware-free.
- **Data types**: `@dataclass(frozen=True, slots=True, kw_only=True)`. Use `Protocol` for injectable COM and tray interfaces.
- **Config**: `config.toml` at the repo root, or `$FMIKE_CONFIG`. The schema rejects unknown and missing keys, so any new key needs a matching update to `config.py`, `config.toml` and `tests/test_config.py`. Device values are **substrings** matched against Windows endpoint names (e.g. `solo = "VG245 ("`).
- **Logging**: `log = logging.getLogger(__name__)`, configured only in `tray.main()`. The CLI talks to the user with `print`.
- **Style**: ruff line length 100, target `py315`. Everything is fully type-annotated (basedpyright `all` mode also covers `tests/`). Use modern syntax (`X | None`, `match`).
- **Line endings** (`.gitattributes`): LF everywhere except `*.ps1`, which is CRLF.
- **Commits**: Conventional Commits, lowercase and imperative (`ci: pin setup-uv ...`).

## Important Files
- `pyproject.toml`: deps (pinned `==`), scripts `fmike = fmike.cli:main` and `fmike-tray = fmike.tray:main`, plus ruff, basedpyright and pytest config.
- `config.toml`: device names, the Banana exe path, and the `presets.clean`/`presets.funny` presets (`gain`, `limit`, `compression`, `label`). The tray detects funny mode from the label.
- `src/fmike/__main__.py`: `python -m fmike` entry point.
- `install.ps1`: user-level bootstrap. It does not use `uv tool install`; the app runs from the repo's `.venv`.
- `uv.lock`: committed. Use `--locked`.

## Runtime/Tooling Preferences
- **Python 3.15 exactly** (`.python-version`; doctor checks it). Use **uv** for everything. Never run pip or a bare `python`.
- Windows only: `winreg`, `winsound`, COM (`pycaw`, `comtypes`, `WScript.Shell`), Voicemeeter Banana. Code that needs Windows should go through `audio.require_windows()` / `NotWindowsError`.
- Type checking uses basedpyright, not mypy. Build backend is `uv_build`.

## Testing & QA
- pytest with `--strict-markers`. Run one test like this: `uv run pytest tests/test_logic.py::test_playback_uses_active_render_device`.
- No mocking libraries. Tests pass plain dataclasses, lambdas and `tmp_path` into the pure functions. Keep it that way: when you add logic, add a pure seam rather than patching COM.
- Not covered: `banana.py`, `cli.py`, the COM parts of `audio.py`, and the pystray loop. Check those manually with `uv run fmike doctor` / `status` on a machine with Banana installed.
- `tests/test_config.py` reads the committed `config.toml`, so keep that file valid.
- Ruff relaxes `S101`, `PLR2004`, `INP001` and `FBT001` in `tests/`.
