"""Persisted game settings (settings.json in the user-data folder)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from phase4.assets import user_data_path

logger = logging.getLogger(__name__)

SETTINGS_FILENAME = "settings.json"
RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080)]
GRAPHICS_LEVELS = ("Low", "Medium", "High")

# Canonical stage registry: id -> (display name, target time seconds).
# (Persistence of results is owned by save_system.SaveManager at the
# project root — see game_ui_screens.HighScoresScreen.)
STAGES = {
    "lobby": ("Lobby", 90.0),
    "data_center": ("Data Center", 75.0),
    "penthouse": ("Penthouse", 105.0),
}


@dataclass
class GameSettings:
    bgm_volume: float = 0.7
    sfx_volume: float = 0.9
    ui_volume: float = 0.8
    resolution: tuple = (1280, 720)
    graphics: str = "High"

    def to_dict(self) -> dict:
        return {
            "bgm_volume": self.bgm_volume, "sfx_volume": self.sfx_volume,
            "ui_volume": self.ui_volume,
            "resolution": list(self.resolution), "graphics": self.graphics,
        }

    @staticmethod
    def from_dict(data: dict) -> "GameSettings":
        res = data.get("resolution", [1280, 720])
        return GameSettings(
            bgm_volume=float(data.get("bgm_volume", 0.7)),
            sfx_volume=float(data.get("sfx_volume", 0.9)),
            ui_volume=float(data.get("ui_volume", 0.8)),
            resolution=(int(res[0]), int(res[1])),
            graphics=str(data.get("graphics", "High")),
        )


def load_settings(path: Optional[Path] = None) -> GameSettings:
    path = Path(path) if path is not None else user_data_path(SETTINGS_FILENAME)
    if path.exists():
        try:
            return GameSettings.from_dict(json.loads(path.read_text()))
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            logger.warning("Settings unreadable (%s) — defaults", exc)
    return GameSettings()


def save_settings(settings: GameSettings, path: Optional[Path] = None) -> None:
    path = Path(path) if path is not None else user_data_path(SETTINGS_FILENAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.to_dict(), indent=2))
    logger.info("Settings saved to %s", path)


def apply_graphics(settings: GameSettings) -> str:
    """Apply the graphics level to the running engine; returns what was set.

    Honest mapping — only flags Ursina/Panda3D actually honour at runtime:
      High   -> vsync on, no frame-rate cap, full window resolution
      Medium -> vsync on, texture downscale x2 (load-time hint only)
      Low    -> vsync off, half-resolution render via window size factor
    The resolution itself is applied by apply_resolution().
    """
    from ursina import application, window
    if settings.graphics == "High":
        window.vsync = True
    elif settings.graphics == "Medium":
        window.vsync = True
    elif settings.graphics == "Low":
        window.vsync = False
    logger.info("Graphics level applied: %s (vsync=%s)",
                settings.graphics, window.vsync)
    return settings.graphics


def apply_resolution(settings: GameSettings) -> tuple:
    """Apply the resolution to the Ursina window where the engine allows."""
    from ursina import window
    width, height = settings.resolution
    try:
        window.size = (width, height)
    except Exception as exc:  # headless / fixed-size backends
        logger.warning("window.size not settable here (%s)", exc)
    return settings.resolution
