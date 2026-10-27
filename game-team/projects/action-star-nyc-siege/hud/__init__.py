"""HUD package for Action Star: NYC Siege 3D.

Exposes HUDManager (live Ursina HUD: HP / Bullet Time bars, time + stunt
score + combo readouts, floating stunt notification feed) as specified in
../HUD-SPEC.md.
"""

from hud.hud_manager import HUDManager, format_time

__all__ = ["HUDManager", "format_time"]
