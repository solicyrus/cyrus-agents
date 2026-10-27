"""BossHealthBar — the dedicated boss HP bar on the HUD (Stage 3).

Cyrus's Stage-3 order: the boss fight shows a DEDICATED boss health bar
on the HUD, bound live to the BossEnemy — not the regular HUD widgets
(hud/hud_manager.py is owned by Stage 1 and is not touched; this is a
small Stage-3 extension living under stage3/).

Behaviour:
  * The bar exists but stays HIDDEN until the boss fight begins
    (``begin_fight(boss)``). It hides again the moment the boss dies or
    ``end_fight()`` is called — it is on screen only during the fight.
  * ``update()`` re-reads ``boss.hud_data()`` every call: the fill bar's
    scale, the HP text and the phase label all track the boss's real
    HP. The rendered values are kept readable (``displayed_fraction``,
    ``fill_scale_x``, ``hp_text_value``) so QA can assert on exactly
    what is on screen — the Stage-3 smoke test does.
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ursina import Entity, Text, camera, color  # noqa: E402

logger = logging.getLogger(__name__)

BAR_FULL_WIDTH = 0.60     # UI units at 100% HP
BAR_Y = 0.415             # vertical centre of the bar (top of screen)


class BossHealthBar:
    """Boss HP bar widget. Construct after the Ursina app exists."""

    def __init__(self) -> None:
        self._boss = None
        self._fight_active = False
        self.displayed_fraction: float = 0.0

        self._name_text = Text(
            text="", parent=camera.ui, position=(0, 0.462),
            origin=(0, 0), scale=1.35, color=color.rgb(255, 205, 90),
            enabled=False)
        self._bg = Entity(parent=camera.ui, model="quad",
                          scale=(BAR_FULL_WIDTH + 0.04, 0.052),
                          position=(0, BAR_Y),
                          color=color.rgb(18, 18, 24), enabled=False)
        # Fill anchored on its left edge: scale_x shrinks with HP.
        self._fill = Entity(parent=camera.ui, model="quad",
                            scale=(BAR_FULL_WIDTH, 0.036),
                            position=(-BAR_FULL_WIDTH / 2, BAR_Y),
                            origin=(-0.5, 0),
                            color=color.rgb(205, 42, 42), enabled=False)
        self._hp_text = Text(
            text="", parent=camera.ui, position=(0, BAR_Y),
            origin=(0, 0), scale=0.95, color=color.white, enabled=False)
        logger.info("BossHealthBar created (hidden until the boss fight)")

    # ------------------------------------------------------------ binding
    def attach(self, boss) -> None:
        """Bind the bar to a BossEnemy (does not show it by itself)."""
        self._boss = boss

    def begin_fight(self, boss=None) -> None:
        """The boss fight starts: bind (if given) and show the bar."""
        if boss is not None:
            self._boss = boss
        if self._boss is None:
            raise ValueError("begin_fight needs a boss (attach one first)")
        self._fight_active = True
        self.update()
        logger.info("Boss fight began — boss bar shown: %s",
                    self._boss.hud_data())

    def end_fight(self) -> None:
        """The fight is over (win or lose): hide the bar."""
        self._fight_active = False
        self._set_visible(False)

    @property
    def boss(self):
        return self._boss

    @property
    def visible(self) -> bool:
        return bool(self._bg.enabled)

    @property
    def fill_scale_x(self) -> float:
        """The fill bar's current on-screen width (UI units)."""
        return float(self._fill.scale_x)

    @property
    def hp_text_value(self) -> str:
        return str(self._hp_text.text)

    # -------------------------------------------------------------- render
    def _set_visible(self, on: bool) -> None:
        for ent in (self._name_text, self._bg, self._fill, self._hp_text):
            ent.enabled = on

    def update(self) -> None:
        """Re-render from the bound boss's live hud_data(). Called per
        frame by the session; hides itself when there is no live boss
        fight to show."""
        if not self._fight_active or self._boss is None \
                or not self._boss.alive:
            if self.visible:
                self._set_visible(False)
            return
        data = self._boss.hud_data()
        frac = max(0.0, min(1.0, float(data["fraction"])))
        self.displayed_fraction = frac
        self._fill.scale_x = BAR_FULL_WIDTH * frac
        # Phase darkening: the bar reddens as the boss enrages.
        self._fill.color = (color.rgb(205, 42, 42) if data["phase"] == 1
                            else color.rgb(225, 84, 30) if data["phase"] == 2
                            else color.rgb(255, 120, 20))
        self._name_text.text = f"{data['name']} — PHASE {data['phase']}"
        self._hp_text.text = (f"{data['hp']:.0f} / {data['max_hp']:.0f} HP")
        self._set_visible(True)
