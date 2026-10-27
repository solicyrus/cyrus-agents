"""Main menu for Action Star: NYC Siege 3D (Phase 4).

MainMenuState is a cinematic 3D menu scene:
  * a stylized NYC tower backdrop built from primitives — a hero tower
    with lit window planes, neighbouring slabs, a street slab;
  * a slow camera drift (update() orbits/raises the camera gently);
  * gold-on-navy UI: START GAME, STAGE SELECT (Lobby 90s / Data Center
    75s / Penthouse 105s), HIGH SCORES, SETTINGS, QUIT.

State-machine interface for the host (game main): assign the callback
attributes (on_start / on_settings / on_scores / on_quit). Every button
routes to a press_*() handler method that records ``last_action`` and
fires the callback — no dead buttons, and tests can drive the handlers
directly without a mouse.
"""

from __future__ import annotations

import logging
import math
from typing import Callable, Optional

from ursina import Button, Entity, Text, application, camera, color, scene

from phase4.game_ui_screens import DIM, GOLD, NAVY_LIGHT, WHITE, _menu_button
from phase4.scores_store import STAGES

logger = logging.getLogger(__name__)

STAGE_ORDER = ("lobby", "data_center", "penthouse")


class MenuResult:
    """What the menu hands back to the game state machine."""

    START = "start"
    STAGE_SELECT = "stage_select"
    SCORES = "scores"
    SETTINGS = "settings"
    QUIT = "quit"


class MainMenuState:
    """The menu scene + UI. Construct after Ursina(); call update(dt)."""

    def __init__(self) -> None:
        self.on_start: Optional[Callable[[str], None]] = None
        self.on_settings: Optional[Callable[[], None]] = None
        self.on_scores: Optional[Callable[[], None]] = None
        self.on_quit: Optional[Callable[[], None]] = None
        self.last_action: Optional[str] = None
        self.last_stage: Optional[str] = None
        self.active = False
        self._drift_t = 0.0

        self.world_root = Entity(parent=scene, enabled=False)
        self.ui_root = Entity(parent=camera.ui, enabled=False)
        self._build_backdrop()
        self._build_ui()
        logger.info("MainMenuState built")

    # ------------------------------------------------------------- backdrop
    def _build_backdrop(self) -> None:
        root = self.world_root
        Entity(parent=root, model="cube", scale=(90, 0.5, 90),
               position=(0, -0.25, 10), color=color.rgb(52, 55, 64))
        # Hero tower straight ahead, windows as thin emissive planes.
        tower = Entity(parent=root, model="cube", scale=(10, 34, 10),
                       position=(0, 17, 26), color=color.rgb(30, 34, 44))
        for row in range(9):
            for col in range(4):
                if (row * 4 + col) % 3 == 0:
                    continue
                Entity(parent=tower, model="quad",
                       scale=(0.14, 0.07), rotation_y=180,
                       position=(-0.36 + col * 0.24, -0.42 + row * 0.1, -0.51),
                       color=color.rgb(255, 196, 92))
        for i, (x, z, h) in enumerate(((-13, 20, 20), (12, 30, 26),
                                       (-9, 36, 14), (15, 14, 11))):
            Entity(parent=root, model="cube", scale=(6, h, 6),
                   position=(x, h / 2, z),
                   color=color.rgb(38 + i * 6, 42 + i * 5, 54 + i * 4))
        # Street glow strip leading to the tower doors.
        Entity(parent=root, model="cube", scale=(3, 0.06, 18),
               position=(0, 0.03, 8), color=color.rgb(90, 78, 40))

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        ui = self.ui_root
        Text(parent=ui, text="ACTION STAR", position=(0, 0.40), scale=4.2,
             color=GOLD, origin=(0, 0))
        Text(parent=ui, text="NYC SIEGE 3D", position=(0, 0.315), scale=2.2,
             color=WHITE, origin=(0, 0))
        Text(parent=ui, text="One tower. One take. Make it a Perfect Take.",
             position=(0, 0.255), scale=1.3, color=DIM, origin=(0, 0))

        self.start_button = _menu_button(ui, "START GAME", 0.13,
                                         self.press_start)
        self.stage_button = _menu_button(ui, "STAGE SELECT", 0.035,
                                         self.press_stage_select)
        self.scores_button = _menu_button(ui, "HIGH SCORES", -0.06,
                                          self.press_scores)
        self.settings_button = _menu_button(ui, "SETTINGS", -0.155,
                                            self.press_settings)
        self.quit_button = _menu_button(ui, "QUIT", -0.25, self.press_quit)

        # Stage-select sub-panel (hidden until STAGE SELECT is pressed).
        self.stage_panel = Entity(parent=ui, enabled=False)
        Text(parent=self.stage_panel, text="SELECT STAGE",
             position=(0, 0.13), scale=2.0, color=GOLD, origin=(0, 0))
        self.stage_buttons = {}
        for i, stage_id in enumerate(STAGE_ORDER):
            name, target = STAGES[stage_id]
            btn = Button(parent=self.stage_panel,
                         text=f"{name.upper()}  —  Target {target:.0f}s",
                         position=(0, 0.03 - i * 0.095), scale=(0.58, 0.075),
                         color=NAVY_LIGHT, text_color=WHITE,
                         highlight_color=GOLD)
            btn.on_click = lambda sid=stage_id: self.press_stage(sid)
            self.stage_buttons[stage_id] = btn
        back = _menu_button(self.stage_panel, "BACK", -0.28,
                            self.press_stage_back, scale=(0.3, 0.06))

    # ------------------------------------------------------------- handlers
    def press_start(self) -> None:
        """START GAME = the first stage (Lobby)."""
        self.press_stage(STAGE_ORDER[0], action=MenuResult.START)

    def press_stage_select(self) -> None:
        self.last_action = MenuResult.STAGE_SELECT
        self.stage_panel.enabled = True
        logger.info("Menu: stage select opened")

    def press_stage_back(self) -> None:
        self.stage_panel.enabled = False

    def press_stage(self, stage_id: str,
                    action: str = MenuResult.STAGE_SELECT) -> None:
        if stage_id not in STAGES:
            raise ValueError(f"unknown stage {stage_id!r}")
        self.last_action = action
        self.last_stage = stage_id
        self.stage_panel.enabled = False
        logger.info("Menu: start stage %s (via %s)", stage_id, action)
        if self.on_start is not None:
            self.on_start(stage_id)

    def press_scores(self) -> None:
        self.last_action = MenuResult.SCORES
        logger.info("Menu: high scores")
        if self.on_scores is not None:
            self.on_scores()

    def press_settings(self) -> None:
        self.last_action = MenuResult.SETTINGS
        logger.info("Menu: settings")
        if self.on_settings is not None:
            self.on_settings()

    def press_quit(self) -> None:
        self.last_action = MenuResult.QUIT
        logger.info("Menu: quit")
        if self.on_quit is not None:
            self.on_quit()
        else:
            application.quit()

    # ------------------------------------------------------------ lifecycle
    def show(self) -> None:
        self.active = True
        self.world_root.enabled = True
        self.ui_root.enabled = True
        camera.position = (0, 3.2, -14)
        camera.rotation = (4, 0, 0)

    def hide(self) -> None:
        self.active = False
        self.world_root.enabled = False
        self.ui_root.enabled = False
        self.stage_panel.enabled = False

    def update(self, dt: float) -> None:
        """Slow cinematic drift: the camera breathes around the tower."""
        if not self.active:
            return
        self._drift_t += dt
        t = self._drift_t
        camera.position = (math.sin(t * 0.11) * 3.2,
                           3.2 + math.sin(t * 0.07) * 0.7,
                           -14 + math.cos(t * 0.09) * 1.2)
        camera.rotation = (4 + math.sin(t * 0.05) * 1.2,
                           math.sin(t * 0.11) * -4.0, 0)
