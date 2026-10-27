"""Asset + user-data paths for Action Star: NYC Siege 3D (Phase 4).

Two different kinds of paths, kept strictly apart:

* ``asset_path(...)`` — READ-ONLY game assets (audio, later models).
  Resolved relative to the running code, or — when frozen by
  PyInstaller — relative to ``sys._MEIPASS`` (the bundle extraction
  dir). Assets are never written to.

* ``user_data_path(...)`` — WRITABLE per-user data (high scores,
  settings). A ``_MEIPASS`` bundle dir is temporary and read-only in
  spirit, so scores live in a stable per-user folder instead:
  ``<home>/.action-star-nyc-siege/`` (or ``$ACTION_STAR_DATA_DIR``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_MODULE_DIR = Path(__file__).resolve().parent


def asset_path(*parts: str) -> Path:
    """Absolute path of a bundled asset, e.g. asset_path('assets', 'bgm_loop.wav').

    Phase-4 assets live beside this module in source form and are added
    to the PyInstaller bundle at the same relative location, so the
    module-relative path works in both worlds; ``_MEIPASS`` wins when
    frozen because ``__file__`` may point into a temp extraction.
    """
    if getattr(sys, "frozen", False):
        return _BUNDLE_DIR.joinpath(*parts)
    return _MODULE_DIR.joinpath(*parts)


def user_data_dir() -> Path:
    """Stable writable folder for scores/settings (created on demand)."""
    override = os.environ.get("ACTION_STAR_DATA_DIR")
    base = Path(override) if override else Path.home() / ".action-star-nyc-siege"
    base.mkdir(parents=True, exist_ok=True)
    return base


def user_data_path(*parts: str) -> Path:
    return user_data_dir().joinpath(*parts)
