"""LevelSelectMenu — the tower floor picker for Action Star: NYC Siege 3D.

Three cards, one per tower floor, driven by a shared
:class:`save_system.SaveManager`:

  * an UNLOCKED card shows the floor title plus the player's record on
    it (best score, best rank, best time — or "No takes yet");
  * a LOCKED card shows a 🔒 and is inert: clicking it fires nothing
    and :meth:`LevelSelectMenu.activate_card` returns ``None``;
  * clicking an unlocked card fires ``on_level_chosen(level_num)``;
  * the Back button fires ``on_back()``.

The menu owns no game state of its own — call :meth:`refresh` after
results are saved and the cards re-read the SaveManager.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Callable, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ursina import Button, Entity, Text, camera, color, destroy  # noqa: E402

from save_system import LEVEL_TITLES, SaveManager  # noqa: E402

logger = logging.getLogger(__name__)

CARD_POSITIONS = {1: -0.46, 2: 0.0, 3: 0.46}
CARD_COLOR = color.rgb32(24, 42, 74)        # deep navy, house palette
CARD_COLOR_HOVER = color.rgb32(46, 74, 122)
LOCKED_COLOR = color.rgb32(52, 54, 62)
GOLD = color.rgb32(201, 162, 39)


class LevelSelectMenu:
    """Level-select screen: three floor cards + a Back button."""

    def __init__(self,
                 save_manager: SaveManager,
                 on_level_chosen: Optional[Callable[[int], None]] = None,
                 on_back: Optional[Callable[[], None]] = None) -> None:
        self.save_manager = save_manager
        self.on_level_chosen = on_level_chosen
        self.on_back = on_back
        self.cards: Dict[int, Button] = {}
        self._entities: list = []

        self.title_text = Text(
            text="SELECT LEVEL — NYC TOWER", origin=(0, 0),
            position=(0, 0.38), scale=2.2, color=GOLD)
        self._entities.append(self.title_text)

        for level_num in sorted(LEVEL_TITLES):
            card = Button(
                text="",
                position=(CARD_POSITIONS[level_num], 0.02),
                scale=(0.4, 0.52),
                color=LOCKED_COLOR,
            )
            card.on_click = self._make_click_handler(level_num)
            self.cards[level_num] = card
            self._entities.append(card)

        self.back_button = Button(
            text="◀ BACK",
            position=(-0.78, -0.42),
            scale=(0.18, 0.07),
            color=CARD_COLOR,
        )
        self.back_button.on_click = self._handle_back
        self._entities.append(self.back_button)

        self.refresh()

    # ------------------------------------------------------------- clicks
    def _make_click_handler(self, level_num: int) -> Callable[[], None]:
        def handler() -> None:
            self.activate_card(level_num)
        return handler

    def activate_card(self, level_num: int) -> Optional[int]:
        """Programmatic card click (also what the on-screen button calls).

        Locked or unknown cards are inert: nothing fires and ``None``
        is returned. An unlocked card fires ``on_level_chosen`` and
        returns the level number.
        """
        if level_num not in LEVEL_TITLES:
            logger.warning("LevelSelect: unknown level %r ignored",
                           level_num)
            return None
        if not self.save_manager.is_unlocked(level_num):
            logger.info("LevelSelect: level %d is locked — click ignored",
                        level_num)
            return None
        logger.info("LevelSelect: level %d chosen", level_num)
        if self.on_level_chosen is not None:
            self.on_level_chosen(level_num)
        return level_num

    def _handle_back(self) -> None:
        logger.info("LevelSelect: back pressed")
        if self.on_back is not None:
            self.on_back()

    # ------------------------------------------------------------ display
    def card_text(self, level_num: int) -> str:
        """The exact text currently shown on one card."""
        return self.cards[level_num].text

    def refresh(self) -> None:
        """Re-read every card from the SaveManager (post-save updates)."""
        for level_num, card in self.cards.items():
            card.text = self._build_card_text(level_num)
            if self.save_manager.is_unlocked(level_num):
                card.color = CARD_COLOR
                card.highlight_color = CARD_COLOR_HOVER
            else:
                card.color = LOCKED_COLOR
                card.highlight_color = LOCKED_COLOR

    def _build_card_text(self, level_num: int) -> str:
        title = LEVEL_TITLES[level_num]
        if not self.save_manager.is_unlocked(level_num):
            return (f"LEVEL {level_num}\n{title}\n\n🔒 LOCKED\n"
                    f"Pass Level {level_num - 1} to unlock")
        record = self.save_manager.get_level_record(level_num)
        if record["best_score"] > 0:
            record_line = (
                f"Best Score: {record['best_score']}\n"
                f"Best Rank: {record['best_rank']}\n"
                f"Best Time: {record['best_time']:.1f}s")
        else:
            record_line = "No takes yet"
        return f"LEVEL {level_num}\n{title}\n\n{record_line}"

    # ------------------------------------------------------------ cleanup
    def destroy(self) -> None:
        """Remove every entity this menu created (screen switch)."""
        for entity in self._entities:
            destroy(entity)
        self._entities.clear()
        self.cards.clear()
