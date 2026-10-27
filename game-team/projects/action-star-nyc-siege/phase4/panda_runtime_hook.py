"""PyInstaller runtime hook — runs before the game entry imports Ursina.

Panda3D loads its display/audio plugins (libpandagl, libp3openal_audio,
...) by name at runtime, so PyInstaller's static analysis cannot see
them. main.spec bundles the plugin .so files into the app root; this
hook points Panda's plugin-path at the bundle root (sys._MEIPASS) so
the frozen binary finds its graphics pipe exactly like a source run.
"""

import os
import sys

if getattr(sys, "frozen", False):
    from panda3d.core import loadPrcFileData

    bundle = sys._MEIPASS
    loadPrcFileData("", f"plugin-path {bundle}")
    # The bundled Config.prc lives under _internal/panda3d/etc.
    prc_dir = os.path.join(bundle, "panda3d", "etc")
    if os.path.isdir(prc_dir):
        os.environ.setdefault("PANDA_PRC_PATH", prc_dir)
