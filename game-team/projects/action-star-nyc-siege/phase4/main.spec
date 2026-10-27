# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Action Star: NYC Siege 3D.

Build (from the project root, either OS):
    python -m PyInstaller phase4/main.spec --noconfirm

Produces dist/ActionStarNYCSiege/ (one-dir). On Windows the entry is
ActionStarNYCSiege.exe; on Linux it is the extensionless binary. Assets
resolve at runtime via phase4/assets.asset_path() (sys._MEIPASS when
frozen). User data (scores/settings) is NEVER bundled — it lives in
<home>/.action-star-nyc-siege/ (see phase4/assets.user_data_path).
"""

from pathlib import Path

import panda3d
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent          # action-star-nyc-siege/
PHASE4 = PROJECT_ROOT / "phase4"

# Panda3D runtime plugins are loaded by NAME (graphics pipe, audio,
# loaders) — static analysis misses them, so bundle them explicitly.
# panda_runtime_hook.py points plugin-path at the bundle root.
PANDA_DIR = Path(panda3d.__file__).parent
PANDA_PLUGINS = [(str(p), ".") for p in
                 list(PANDA_DIR.glob("libp3*.so")) +
                 list(PANDA_DIR.glob("libpandagl.so")) +
                 list(PANDA_DIR.glob("libp3*.dll")) +
                 list(PANDA_DIR.glob("libpandagl.dll"))]

datas = [
    # Game audio: normal + bullet_time/ variants, manifest included.
    (str(PHASE4 / "assets"), "phase4/assets"),
]
# Ursina ships shaders/textures/fonts inside its package — bundle them.
datas += collect_data_files("ursina")
datas += collect_data_files("panda3d")

hiddenimports = []
hiddenimports += collect_submodules("ursina")
hiddenimports += [
    "phase4.game_entry", "phase4.main_menu", "phase4.game_ui_screens",
    "phase4.sound_manager", "phase4.scores_store", "phase4.game_settings",
    "phase4.assets", "logic.take_rating", "logic.stunt_manager",
    "logic.timer_manager", "hud.hud_manager",
]

a = Analysis(
    [str(PHASE4 / "game_entry.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=PANDA_PLUGINS,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(PHASE4 / "panda_runtime_hook.py")],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ActionStarNYCSiege",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # keep the console: QA logs stay visible
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ActionStarNYCSiege",
)
