"""UI screens for Action Star: NYC Siege 3D (Phase 4).

Three screens, each owning a root entity under camera.ui and exposing
show()/hide() plus plain handler methods (so hosts and tests drive them
without simulating a mouse):

  * SettingsMenu   — BGM/SFX/UI volume sliders (live-applied to the
                     SoundManager + persisted), resolution selector,
                     graphics selector, and the key-guide panel with the
                     game's real controls (from level1/main.py).
  * VictoryScreen  — the animated Final Take report card. One component,
                     state-driven: outcome='victory' renders the ranked
                     card (rank, cinematic title, S_total breakdown);
                     outcome='game_over' renders the F / "Re-take
                     Required" state. RE-TAKE and BACK TO MENU actions.
  * HighScoresScreen — per-stage bests read through
                     save_system.SaveManager (project root), or an honest
                     "No takes yet" line per stage when no record exists.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ursina import Button, Entity, Slider, Text, camera, color, curve, invoke

from phase4.game_settings import (GRAPHICS_LEVELS, RESOLUTIONS, STAGES,
                                  GameSettings, apply_graphics,
                                  apply_resolution, save_settings)

logger = logging.getLogger(__name__)

NAVY = color.rgb(11, 36, 64)
NAVY_LIGHT = color.rgb(18, 52, 92)
GOLD = color.rgb(201, 162, 39)
WHITE = color.white
DIM = color.rgb(170, 182, 200)

# The game's real controls — copied from level1/main.py (the shipped
# input mapping), shown verbatim in the settings key-guide panel.
KEY_GUIDE = (
    "KEY GUIDE\n"
    "W A S D ........ Move\n"
    "Mouse .......... Aim / Look\n"
    "Left Mouse ..... Shoot\n"
    "Right Mouse / F  Melee\n"
    "C .............. Slide\n"
    "SPACE .......... Wall Jump (in a wall-run)\n"
    "L-SHIFT ........ Bullet Time\n"
    "R .............. Reload\n"
    "ESC ............ Pause / Quit"
)


def _panel(parent, y=0.0, scale=(1.15, 0.86)) -> Entity:
    return Entity(parent=parent, model="quad", color=NAVY,
                  position=(0, y), scale=scale, z=0.01)


def _title(parent, text_value: str, y: float, scale: float = 3.2) -> Text:
    return Text(parent=parent, text=text_value, position=(0, y), scale=scale,
                color=GOLD, origin=(0, 0))


def _menu_button(parent, text_value: str, y: float, handler,
                 scale=(0.52, 0.075)) -> Button:
    btn = Button(parent=parent, text=text_value, position=(0, y),
                 scale=scale, color=NAVY_LIGHT, text_color=WHITE,
                 highlight_color=GOLD)
    btn.on_click = handler
    return btn


class SettingsMenu:
    """Volume + resolution + graphics + key guide. Changes persist."""

    def __init__(self, settings: GameSettings, sound_manager=None,
                 on_back: Optional[Callable[[], None]] = None) -> None:
        self.settings = settings
        self.sound = sound_manager
        self.on_back = on_back or (lambda: None)
        self.root = Entity(parent=camera.ui, enabled=False)
        _panel(self.root)
        _title(self.root, "SETTINGS", 0.36, scale=2.6)

        self.sliders = {}
        rows = (("BGM VOLUME", "bgm", "bgm_volume", 0.24),
                ("SFX VOLUME", "sfx", "sfx_volume", 0.13),
                ("UI VOLUME", "ui", "ui_volume", 0.02))
        for label, channel, attr, y in rows:
            Text(parent=self.root, text=label, position=(-0.5, y + 0.035),
                 scale=1.4, color=WHITE)
            slider = Slider(parent=self.root, min=0, max=100,
                            default=int(getattr(settings, attr) * 100),
                            step=1, position=(-0.28, y), scale=(0.55, 0.03),
                            dynamic=True)
            slider.on_value_changed = \
                lambda ch=channel, at=attr, s=slider: \
                self._on_volume(ch, at, s.value)
            self.sliders[channel] = slider

        Text(parent=self.root, text="RESOLUTION", position=(-0.5, -0.12),
             scale=1.4, color=WHITE)
        self.resolution_buttons = {}
        for i, (w, h) in enumerate(RESOLUTIONS):
            btn = Button(parent=self.root, text=f"{w}x{h}",
                         position=(-0.34 + i * 0.3, -0.17),
                         scale=(0.26, 0.055), color=NAVY_LIGHT,
                         text_color=WHITE, highlight_color=GOLD)
            btn.on_click = lambda rw=w, rh=h: self.set_resolution(rw, rh)
            self.resolution_buttons[(w, h)] = btn

        Text(parent=self.root, text="GRAPHICS", position=(-0.5, -0.25),
             scale=1.4, color=WHITE)
        self.graphics_buttons = {}
        for i, level in enumerate(GRAPHICS_LEVELS):
            btn = Button(parent=self.root, text=level,
                         position=(-0.34 + i * 0.3, -0.30),
                         scale=(0.26, 0.055), color=NAVY_LIGHT,
                         text_color=WHITE, highlight_color=GOLD)
            btn.on_click = lambda lv=level: self.set_graphics(lv)
            self.graphics_buttons[level] = btn

        self.key_guide = Text(parent=self.root, text=KEY_GUIDE,
                              position=(0.13, -0.02), scale=1.15, color=DIM)
        _menu_button(self.root, "BACK", -0.40, self.press_back,
                     scale=(0.3, 0.06))
        self._mark_selectors()
        logger.info("SettingsMenu built")

    # ------------------------------------------------------------ handlers
    def _on_volume(self, channel: str, attr: str, raw_value) -> None:
        value = max(0.0, min(1.0, float(raw_value) / 100.0))
        setattr(self.settings, attr, value)
        if self.sound is not None:
            self.sound.set_volume(channel, value)
        save_settings(self.settings)
        logger.info("Setting %s = %.2f", attr, value)

    def set_bgm_volume(self, value: float) -> None:
        self.sliders["bgm"].value = int(value * 100)
        self._on_volume("bgm", "bgm_volume", int(value * 100))

    def set_resolution(self, width: int, height: int) -> None:
        self.settings.resolution = (int(width), int(height))
        apply_resolution(self.settings)
        save_settings(self.settings)
        self._mark_selectors()
        logger.info("Resolution set to %dx%d", width, height)

    def set_graphics(self, level: str) -> None:
        if level not in GRAPHICS_LEVELS:
            raise ValueError(f"unknown graphics level {level!r}")
        self.settings.graphics = level
        apply_graphics(self.settings)
        save_settings(self.settings)
        self._mark_selectors()
        logger.info("Graphics set to %s", level)

    def press_back(self) -> None:
        self.hide()
        self.on_back()

    def _mark_selectors(self) -> None:
        for res, btn in self.resolution_buttons.items():
            btn.color = GOLD if res == self.settings.resolution \
                else NAVY_LIGHT
        for level, btn in self.graphics_buttons.items():
            btn.color = GOLD if level == self.settings.graphics \
                else NAVY_LIGHT

    # ------------------------------------------------------------ visibility
    def show(self) -> None:
        self.root.enabled = True

    def hide(self) -> None:
        self.root.enabled = False

    @property
    def visible(self) -> bool:
        return bool(self.root.enabled)


class VictoryScreen:
    """Final Take report card — victory (ranked) or game over (F state)."""

    def __init__(self, sound_manager=None,
                 on_retake: Optional[Callable[[str], None]] = None,
                 on_menu: Optional[Callable[[], None]] = None) -> None:
        self.sound = sound_manager
        self.on_retake = on_retake or (lambda stage_id: None)
        self.on_menu = on_menu or (lambda: None)
        self.stage_id: Optional[str] = None
        self.outcome: Optional[str] = None
        self.root = Entity(parent=camera.ui, enabled=False)
        _panel(self.root, scale=(1.2, 0.9))

        self.heading = _title(self.root, "", 0.38, scale=2.4)
        self.rank_text = Text(parent=self.root, text="", position=(0, 0.22),
                              scale=7.0, color=GOLD, origin=(0, 0))
        self.title_text = Text(parent=self.root, text="", position=(0, 0.08),
                               scale=2.2, color=WHITE, origin=(0, 0))
        self.breakdown = Text(parent=self.root, text="", position=(0, -0.06),
                              scale=1.5, color=WHITE, origin=(0, 0))
        self.detail = Text(parent=self.root, text="", position=(0, -0.22),
                           scale=1.25, color=DIM, origin=(0, 0))
        self.retake_button = _menu_button(self.root, "RE-TAKE", -0.35,
                                          self.press_retake,
                                          scale=(0.34, 0.065))
        self.menu_button = _menu_button(self.root, "BACK TO MENU", -0.43,
                                        self.press_menu, scale=(0.34, 0.065))
        logger.info("VictoryScreen built")

    # ---------------------------------------------------------------- show
    def show_result(self, result, run_record: dict) -> None:
        """result: logic.take_rating.TakeResult; run_record: run facts.

        State-driven outcome: a completed take with rank F — or a failed
        run flagged in run_record — renders the Game Over state; anything
        else renders the ranked victory card.
        """
        self.stage_id = run_record["stage_id"]
        failed = (not run_record.get("completed", True)) \
            or result.rank == "F"
        self.outcome = "game_over" if failed else "victory"

        stage_name = run_record.get("stage_name", self.stage_id)
        t_actual = float(run_record["t_actual"])
        t_target = float(run_record["t_target"])
        combo_peak = float(run_record.get("combo_peak",
                                          result.combo_multiplier))
        lines = [
            f"S_time ......... {result.s_time:,}",
            f"S_stunt ........ {result.stunt_base:,}  x {combo_peak:.1f} combo"
            f" = {result.stunt_component:,}",
            f"S_total ........ {result.total:,}",
        ]
        breakdown_lines = list(run_record.get("stunt_breakdown", []))

        if self.outcome == "game_over":
            self.heading.text = "GAME OVER"
            self.rank_text.text = "F"
            self.rank_text.color = color.rgb(200, 60, 50)
            self.title_text.text = "Re-take Required"
        else:
            self.heading.text = f"TAKE COMPLETE — {stage_name.upper()}"
            self.rank_text.text = result.rank
            self.rank_text.color = GOLD
            self.title_text.text = result.title
        self.breakdown.text = "\n".join(lines)
        detail = [f"Time {t_actual:.1f}s / Target {t_target:.0f}s",
                  f"Combo peak x{combo_peak:.1f}"]
        detail += breakdown_lines
        self.detail.text = "\n".join(detail)

        self.root.enabled = True
        self._reveal()
        if self.sound is not None:
            self.sound.play_ui("rank")
        logger.info("VictoryScreen: %s rank %s total %d",
                    self.outcome, result.rank, result.total)

    def _reveal(self) -> None:
        """Staggered fade/scale-in — the card 'animates' onto the screen."""
        parts = [self.heading, self.rank_text, self.title_text,
                 self.breakdown, self.detail]
        for i, part in enumerate(parts):
            part.alpha = 0.0
            invoke(setattr, part, "alpha", 1.0, delay=0.12 * i)
        self.rank_text.scale = 0.2
        self.rank_text.animate_scale(7.0, duration=0.45, curve=curve.out_expo)

    # ------------------------------------------------------------ handlers
    def press_retake(self) -> None:
        self.hide()
        if self.stage_id is not None:
            self.on_retake(self.stage_id)

    def press_menu(self) -> None:
        self.hide()
        self.on_menu()

    def hide(self) -> None:
        self.root.enabled = False

    @property
    def visible(self) -> bool:
        return bool(self.root.enabled)


# Stage id -> SaveManager level number (the tower's floor order).
LEVEL_BY_STAGE = {"lobby": 1, "data_center": 2, "penthouse": 3}


def _record_fields(record) -> Optional[dict]:
    """Normalize a SaveManager level record to display fields.

    Persistence is owned by save_system.SaveManager at the project
    root (user_progress.json); the screen reads ONLY through
    SaveManager.get_level_record(level_num). save_system.py has
    landed, so this helper uses its REAL record keys (best_score /
    best_time / best_rank / title — tightened 2026-10-27, the fix the
    Phase-4 report flagged). A fresh record (score 0, rank "N/A")
    reads as "no record".
    """
    if not isinstance(record, dict):
        return None
    total = record.get("best_score")
    rank = str(record.get("best_rank", ""))
    if total is None or (int(total) == 0 and rank in ("", "N/A")):
        return None
    return {
        "total": int(total),
        "rank": rank,
        "title": str(record.get("title", "")),
        "time": float(record.get("best_time", 0.0)),
    }


class HighScoresScreen:
    """Per-stage bests read through save_system.SaveManager.

    Honest 'No takes yet' line for any stage without a record.
    """

    def __init__(self, save_manager=None,
                 on_back: Optional[Callable[[], None]] = None) -> None:
        self.save = save_manager   # a SaveManager, or None -> lazy import
        self.on_back = on_back or (lambda: None)
        self.root = Entity(parent=camera.ui, enabled=False)
        _panel(self.root, scale=(1.2, 0.9))
        _title(self.root, "HIGH SCORES", 0.38, scale=2.6)
        self.lines = Text(parent=self.root, text="", position=(0, 0.05),
                          scale=1.5, color=WHITE, origin=(0, 0))
        _menu_button(self.root, "BACK", -0.40, self.press_back,
                     scale=(0.3, 0.06))
        logger.info("HighScoresScreen built")

    def _manager(self):
        if self.save is None:
            from save_system import SaveManager  # project-root module
            self.save = SaveManager()
        return self.save

    def refresh(self) -> None:
        manager = self._manager()
        rows = []
        for stage_id, (name, target) in STAGES.items():
            fields = _record_fields(
                manager.get_level_record(LEVEL_BY_STAGE[stage_id]))
            if fields is None:
                rows.append(f"{name.upper():<14} No takes yet")
            else:
                rows.append(
                    f"{name.upper():<14} {fields['rank']}  {fields['title']}\n"
                    f"{'':<14} S_total {fields['total']:,}   "
                    f"Best time {fields['time']:.1f}s / {target:.0f}s")
        self.lines.text = "\n\n".join(rows)

    def show(self) -> None:
        self.refresh()
        self.root.enabled = True

    def hide(self) -> None:
        self.root.enabled = False

    def press_back(self) -> None:
        self.hide()
        self.on_back()

    @property
    def visible(self) -> bool:
        return bool(self.root.enabled)
