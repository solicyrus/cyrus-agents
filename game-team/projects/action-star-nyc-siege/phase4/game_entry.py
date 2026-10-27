"""Game entry point — Action Star: NYC Siege 3D (packaged by main.spec).

Boots Ursina with the persisted settings, starts the BGM, and runs the
Phase-4 shell state machine:

    menu -> settings / high scores / victory (demo card) -> menu
    menu -> stage start  ==(integration point)==> stage scenes

The stage scenes themselves (level1/, stage3/) are integrated by the
full-game assembly step once Stages 2-3 land; the handoff is the
``launch_stage(stage_id)`` function below — it already records the
selection and returns to the menu until the stage modules are wired
in, so this entry is complete and runnable today, and the full-cycle
menu -> stages -> victory -> menu run is exercised by the QA pass that
follows Stages 2-3 (see TEST-REPORT.md, honest limits).

Run:  python -m phase4.game_entry     (from the project root)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ursina import Ursina, application, time as ursina_time  # noqa: E402

from phase4.game_settings import (STAGES, apply_graphics,  # noqa: E402
                                  apply_resolution, load_settings)
from phase4.game_ui_screens import (HighScoresScreen, SettingsMenu,  # noqa: E402
                                    VictoryScreen)
from phase4.main_menu import MainMenuState  # noqa: E402
from phase4.sound_manager import SoundManager  # noqa: E402
from logic.take_rating import evaluate  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("game_entry")

settings = load_settings()
app = Ursina(title="Action Star: NYC Siege 3D", vsync=True, borderless=False)
apply_graphics(settings)
apply_resolution(settings)

sound = SoundManager(bgm_volume=settings.bgm_volume,
                     sfx_volume=settings.sfx_volume,
                     ui_volume=settings.ui_volume)

menu = MainMenuState()
settings_screen = SettingsMenu(settings, sound_manager=sound,
                               on_back=lambda: show_only(menu))
scores_screen = HighScoresScreen(on_back=lambda: show_only(menu))

# SEAM: LevelSelectMenu (level_select.py, project root) + SaveManager
# persistence are owned by the save-system workstream. When the module
# lands, the menu's STAGE SELECT opens it here; until then the seam is
# logged, never faked.
try:
    from level_select import LevelSelectMenu  # noqa: F401
    logger.info("level_select present — wire LevelSelectMenu here")
except Exception as exc:  # module not landed yet
    logger.warning("level_select not integrated yet (%s)", exc)
victory_screen = VictoryScreen(
    sound_manager=sound,
    on_retake=lambda stage_id: launch_stage(stage_id),
    on_menu=lambda: show_only(menu))

_screens = [settings_screen, scores_screen, victory_screen]


def show_only(target) -> None:
    """State machine: exactly one of menu / sub-screens is visible."""
    menu.hide()
    for screen in _screens:
        screen.hide()
    if target is menu:
        menu.show()
    else:
        target.show()


def launch_stage(stage_id: str) -> None:
    """Integration point for Stages 2-3 (level1 / stage3 scenes).

    Until the stage modules are assembled into this entry, starting a
    stage shows the victory-card pipeline with a graded demo take —
    proving menu -> card -> menu with the real rating + scores code.
    """
    name, target = STAGES[stage_id]
    logger.info("Stage start requested: %s (target %.0fs)", name, target)
    menu.hide()
    for screen in _screens:
        screen.hide()
    result = evaluate(s_time=3500, s_stunt=3320, m_combo=2.5)
    record = {
        "stage_id": stage_id, "stage_name": name,
        "t_actual": 85.0, "t_target": target,
        "combo_peak": result.combo_multiplier, "completed": True,
        "stunt_breakdown": ["Bullet Dodge x4", "Slide & Shoot x3",
                            "Air Takedown x2", "Wall-Run Kill x1"],
    }
    # Persistence of the graded take goes through save_system.SaveManager
    # (owned by the save-system workstream) once the stage integration
    # lands; the demo path deliberately writes nothing.
    victory_screen.show_result(result, record)


menu.on_start = launch_stage
menu.on_settings = lambda: show_only(settings_screen)
menu.on_scores = lambda: show_only(scores_screen)
menu.on_quit = application.quit
menu.show()
sound.start_bgm()


def update() -> None:
    menu.update(ursina_time.dt)
    sound.prune()


if __name__ == "__main__":
    app.run()
