# Packaging — Action Star: NYC Siege 3D

## What is built and proven

`phase4/build_executable.py` drives PyInstaller with `phase4/main.spec`
and produces a **one-dir** build:

    dist/ActionStarNYCSiege/           (Linux: binary `ActionStarNYCSiege`,
                                        Windows: `ActionStarNYCSiege.exe`)

Verified in this sandbox (2026-10-27): the **Linux** build completed
(PyInstaller 6.22.3, ~158 MB dist) and the produced binary was
smoke-run headless under xvfb — it booted the real entry
(`phase4/game_entry.py`), logging `SoundManager ready`,
`MainMenuState built`, `BGM started`, with all audio assets resolved
from the bundle (`_internal/phase4/assets/`, normal + bullet_time/).

Two non-obvious things the spec handles (both found by failing first):
  * Ursina 8.3's `Audio()` loads clips reliably only from `pathlib.Path`
    objects — SoundManager passes Paths (see sound_manager.py).
  * Panda3D loads its display/audio plugins (libpandagl,
    libp3openal_audio) **by name at runtime**; static analysis misses
    them and the frozen app dies with "No graphics pipe is available!".
    main.spec bundles the plugins explicitly and
    `panda_runtime_hook.py` sets Panda's plugin-path to the bundle root.

## The Windows .exe — read this honestly

**A Windows .exe cannot be produced from this Linux sandbox.**
PyInstaller does not cross-compile: an .exe must be built on Windows
(PyInstaller embeds the host OS's bootloader and binaries). No .exe
exists yet and none is claimed.

### One-command Windows build

On a Windows machine with Python 3.12 installed:

    git clone https://github.com/solicyrus/cyrus-agents
    cd cyrus-agents\game-team\projects\action-star-nyc-siege
    py -m venv .venv
    .venv\Scripts\pip install ursina numpy pyinstaller
    .venv\Scripts\python phase4\generate_audio_assets.py
    .venv\Scripts\python phase4\build_executable.py

Result: `dist\ActionStarNYCSiege\ActionStarNYCSiege.exe`
(the same spec works unchanged — plugin globs cover .dll as well).

## Paths at runtime

* Assets (read-only): `phase4.assets.asset_path()` — resolves against
  `sys._MEIPASS` when frozen, the module folder in source form.
* User data (writable): high scores + settings live in
  `<home>\.action-star-nyc-siege\` (`ACTION_STAR_DATA_DIR` overrides).
  They are never written into the bundle.
