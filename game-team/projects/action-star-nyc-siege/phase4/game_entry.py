"""Game entry point — Action Star: NYC Siege 3D (packaged by main.spec).

Boots Ursina with the persisted settings, starts the BGM, and runs the
game shell state machine:

    menu -> settings / high scores / level select -> menu
    menu -> START GAME (or a level-select floor) -> FullGamePipeline
         -> Lobby -> elevator -> Data Center -> elevator -> Penthouse
         -> Final Take card (VictoryScreen) -> BACK TO MENU -> menu

FINAL WIRING (Cyrus's order, 2026-10-27): the menu's stage start no
longer shows a demo take. ``launch_stage()`` constructs the real
``full_game_pipeline.FullGamePipeline`` — START GAME starts the full
three-floor run at Floor 1; a floor chosen in the LevelSelectMenu
starts the pipeline at that floor (the pipeline's level-select rule:
fresh RunState, and a locked floor is refused by the shared
SaveManager). The pipeline receives THIS entry's VictoryScreen and a
SaveBridge bound to the entry's one shared SaveManager — the same
instance the level-select cards and the high-scores screen read — so
records written by a run are the records the menus show. VictoryScreen's
BACK TO MENU disposes the pipeline and returns to the live menu;
RE-TAKE restarts the run from its starting floor.

Frame driving lives in :func:`pump`: the packaged game calls it from
Ursina's ``update()`` hook with keyboard/mouse input; tests register an
input provider via :func:`set_input_provider` and pump the same code
path with scripted input (see test_full_cycle.py).

Run:  python -m phase4.game_entry     (from the project root)
"""

from __future__ import annotations

import logging
import math
import sys
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ursina import Ursina, Vec3, application, held_keys, mouse  # noqa: E402
from ursina import time as ursina_time  # noqa: E402

from full_game_pipeline import FullGamePipeline  # noqa: E402
from level1.player_controller_3d import PlayerInput  # noqa: E402
from level_select import LevelSelectMenu  # noqa: E402
from pipeline_state import FLOOR_TABLE, SaveBridge  # noqa: E402
from save_system import SaveManager  # noqa: E402

from phase4.game_settings import (apply_graphics, apply_resolution,  # noqa: E402
                                  load_settings)
from phase4.game_ui_screens import (HighScoresScreen, SettingsMenu,  # noqa: E402
                                    VictoryScreen)
from phase4.main_menu import MainMenuState  # noqa: E402
from phase4.sound_manager import SoundManager  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("game_entry")

# stage id <-> floor number (pipeline_state.FLOOR_TABLE is canonical).
STAGE_ID_BY_FLOOR = {num: stage_id
                     for num, stage_id, _name, _t in FLOOR_TABLE}
FLOOR_BY_STAGE_ID = {stage_id: num
                     for num, stage_id in STAGE_ID_BY_FLOOR.items()}

settings = load_settings()
app = Ursina(title="Action Star: NYC Siege 3D", vsync=True, borderless=False)
apply_graphics(settings)
apply_resolution(settings)

sound = SoundManager(bgm_volume=settings.bgm_volume,
                     sfx_volume=settings.sfx_volume,
                     ui_volume=settings.ui_volume)

# ONE shared SaveManager for the whole shell: level-select cards, the
# high-scores screen and the pipeline's SaveBridge all read/write the
# same instance (hence the same user_progress.json).
save_manager = SaveManager()
save_bridge = SaveBridge()
save_bridge.manager = save_manager


class _LevelSelectHost:
    """show()/hide() adapter for level_select.LevelSelectMenu.

    MainMenuState's seam (attach_level_select) expects show()/hide();
    LevelSelectMenu owns loose UI entities instead of a root, so the
    host toggles them. show() refreshes the cards from the shared
    SaveManager first, so post-run records/unlocks are what the
    player sees.
    """

    def __init__(self, level_menu: LevelSelectMenu) -> None:
        self.menu = level_menu

    def show(self) -> None:
        self.menu.refresh()
        for ent in self.menu._entities:
            ent.enabled = True

    def hide(self) -> None:
        for ent in self.menu._entities:
            ent.enabled = False


menu = MainMenuState()
settings_screen = SettingsMenu(settings, sound_manager=sound,
                               on_back=lambda: show_only(menu))
scores_screen = HighScoresScreen(save_manager=save_manager,
                                 on_back=lambda: show_only(menu))
victory_screen = VictoryScreen(
    sound_manager=sound,
    on_retake=lambda stage_id: _retake_run(stage_id),
    on_menu=lambda: _back_to_menu())

_screens = [settings_screen, scores_screen, victory_screen]

level_select = LevelSelectMenu(
    save_manager,
    on_level_chosen=lambda num: menu.press_stage(STAGE_ID_BY_FLOOR[num]),
    on_back=lambda: show_only(menu))
level_select_host = _LevelSelectHost(level_select)
menu.attach_level_select(level_select_host)
level_select_host.hide()          # cards stay hidden until STAGE SELECT


def show_only(target) -> None:
    """State machine: exactly one of menu / sub-screens is visible."""
    menu.hide()
    for screen in _screens:
        screen.hide()
    if target is menu:
        menu.show()
    else:
        target.show()


# ===========================================================================
# Run control — the START -> pipeline wiring
# ===========================================================================
_run = {"pipeline": None, "start_floor": 1}
_input_provider: Optional[Callable[[], PlayerInput]] = None


def active_pipeline() -> Optional[FullGamePipeline]:
    """The live FullGamePipeline, or None when the shell is in menus."""
    return _run["pipeline"]


def set_input_provider(provider: Optional[Callable[[], PlayerInput]]) -> None:
    """Register a scripted input source for pump() (tests/tools).

    The provider is called once per pumped frame while a run is live
    and must return a PlayerInput. None restores keyboard/mouse play.
    """
    global _input_provider
    _input_provider = provider


def launch_stage(stage_id: str) -> None:
    """Menu stage start (START GAME or a level-select choice).

    Starts the real FullGamePipeline at the stage's floor: 'lobby'
    (START GAME) runs the full three-floor chain; a level-select
    floor starts there under the pipeline's level-select rule.
    """
    _start_run(FLOOR_BY_STAGE_ID[stage_id])


def _start_run(start_floor: int) -> None:
    _dispose_run()
    menu.hide()
    for screen in _screens:
        screen.hide()
    _run["start_floor"] = start_floor
    _run["pipeline"] = FullGamePipeline(
        start_floor=start_floor,
        victory_screen=victory_screen,
        save_bridge=save_bridge)
    _set_mouse_locked(True)
    logger.info("Run started at floor %d (FullGamePipeline)", start_floor)


def _dispose_run() -> None:
    pipeline = _run["pipeline"]
    if pipeline is not None:
        pipeline.dispose()
        _run["pipeline"] = None
    sound.set_bullet_time(False)


def _back_to_menu() -> None:
    """VictoryScreen BACK TO MENU: end the run, revive the menu."""
    _dispose_run()
    _set_mouse_locked(False)
    show_only(menu)
    logger.info("Returned to main menu")


def _retake_run(stage_id: str) -> None:
    """VictoryScreen RE-TAKE: restart from the run's starting floor."""
    logger.info("Re-take requested (card stage %r) — restarting floor %d",
                stage_id, _run["start_floor"])
    _start_run(_run["start_floor"])


def _set_mouse_locked(locked: bool) -> None:
    try:
        mouse.locked = locked
    except Exception as exc:  # headless backends have no pointer lock
        logger.debug("mouse.locked=%s unavailable here (%s)", locked, exc)


# ===========================================================================
# Human input (keyboard/mouse) — used when no provider is registered
# ===========================================================================
_edges = {"slide": False, "melee": False, "bullet_time": False,
          "reload": False}
_aim = {"yaw": 0.0, "pitch": 0.0}


def input(key):  # noqa: A001 — Ursina's input hook name
    if key in ("left shift", "shift"):
        _edges["bullet_time"] = True
    elif key == "c":
        _edges["slide"] = True
    elif key in ("right mouse down", "f"):
        _edges["melee"] = True
    elif key == "r":
        _edges["reload"] = True
    elif key == "escape" and _run["pipeline"] is not None:
        _back_to_menu()


def _keyboard_input() -> PlayerInput:
    pipeline = _run["pipeline"]
    if pipeline is None or pipeline.phase != "floor":
        return PlayerInput()
    try:
        vel = getattr(mouse, "velocity", None)
        vx = float(vel[0]) if vel is not None else float(
            getattr(mouse, "velocity_x", 0.0))
        vy = float(vel[1]) if vel is not None else float(
            getattr(mouse, "velocity_y", 0.0))
        _aim["yaw"] += vx * 55.0
        _aim["pitch"] = max(-40.0, min(40.0, _aim["pitch"] - vy * 55.0))
    except Exception:
        pass
    yaw = math.radians(_aim["yaw"])
    fwd = Vec3(math.sin(yaw), 0, math.cos(yaw))
    right = Vec3(math.cos(yaw), 0, -math.sin(yaw))
    move = Vec3(0, 0, 0)
    if held_keys["w"]:
        move += fwd
    if held_keys["s"]:
        move -= fwd
    if held_keys["d"]:
        move += right
    if held_keys["a"]:
        move -= right
    inp = PlayerInput(
        move=move,
        aim_yaw=_aim["yaw"],
        aim_pitch=_aim["pitch"],
        shoot=bool(held_keys["left mouse"]),
        melee=_edges["melee"],
        slide=_edges["slide"],
        bullet_time=_edges["bullet_time"],
        reload=_edges["reload"],
    )
    for name in _edges:
        _edges[name] = False
    return inp


# ===========================================================================
# Frame driving
# ===========================================================================
def pump(dt: float) -> None:
    """Advance the shell by one frame (menu drift, run, audio house-
    keeping). The single code path for live play and for tests."""
    sound.prune()
    pipeline = _run["pipeline"]
    if pipeline is None:
        menu.update(dt)
        return
    inp = _input_provider() if _input_provider is not None \
        else _keyboard_input()
    pipeline.tick(min(dt, 0.05), inp)
    session = pipeline.session
    if session is not None:
        sound.set_bullet_time(session.player.bt_active)


def update() -> None:
    pump(ursina_time.dt)


menu.on_start = launch_stage
menu.on_settings = lambda: show_only(settings_screen)
menu.on_scores = lambda: show_only(scores_screen)
menu.on_quit = application.quit
menu.show()
sound.start_bgm()


if __name__ == "__main__":
    app.run()
