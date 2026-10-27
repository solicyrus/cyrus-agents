"""IntroCard — the fiction slate shown on START, before Floor 1.

The game's official fiction (Cyrus, 2026-10-27; GDD §6b): you are THE
ACTION STAR, a professional stunt actor auditioning for the lead role
in New York's biggest action film. Every floor is a LIVE TAKE on a
working film set, and the Director grades the take S/A/B/C.

This card is that slate: it appears when a run starts, carries the
fiction in three lines, and dismisses into the pipeline on a click, on
any key (the host routes keys here), programmatically via
:meth:`dismiss`, or on its own after ``AUTO_HOLD_S`` seconds so
scripted flows and tests can never hang on it. While it is up, the
host (phase4/game_entry) pauses the floor timer — TimerManager's
pause() exists for exactly this: menus and cutscenes — so the take
clock only starts when the slate drops.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Callable, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ursina import Button, Entity, Text, camera, color  # noqa: E402

logger = logging.getLogger(__name__)

GOLD = color.rgb(201, 162, 39)
NAVY = color.rgb(11, 20, 38)
WHITE = color.white
DIM = color.rgb(170, 182, 200)

TITLE_TEXT = "THE ACTION STAR"
BODY_TEXT = (
    "You are THE ACTION STAR — a professional stunt actor auditioning\n"
    "for the lead in New York's biggest action film.\n"
    "Every floor is a LIVE TAKE on a working film set.\n"
    "The Director is watching. Impress the Director. Earn your S."
)
PROMPT_TEXT = "CLICK OR PRESS ANY KEY — ROLL CAMERAS"

AUTO_HOLD_S = 3.0    # the slate holds this long, then drops on its own


class IntroCard:
    """The pre-take fiction slate. Construct after the Ursina app."""

    def __init__(self,
                 on_dismiss: Optional[Callable[[], None]] = None) -> None:
        self.on_dismiss = on_dismiss or (lambda: None)
        self.root = Entity(parent=camera.ui, enabled=False)
        # Full-screen slate; the Button IS the click-to-dismiss surface.
        self._slate = Button(parent=self.root, model="quad",
                             scale=(2.2, 1.3), position=(0, 0, 0.02),
                             color=NAVY, text="")
        self._slate.on_click = self.dismiss
        self.title = Text(parent=self.root, text=TITLE_TEXT,
                          position=(0, 0.26, -0.01), origin=(0, 0),
                          scale=3.6, color=GOLD)
        self.body = Text(parent=self.root, text=BODY_TEXT,
                         position=(0, 0.10, -0.01), origin=(0, 0.5),
                         scale=1.5, color=WHITE)
        self.prompt = Text(parent=self.root, text=PROMPT_TEXT,
                           position=(0, -0.30, -0.01), origin=(0, 0),
                           scale=1.4, color=DIM)
        self.visible: bool = False
        self.frames: int = 0          # frames actually shown (QA proof)
        self._held_s: float = 0.0
        logger.info("IntroCard built")

    # ------------------------------------------------------------ control
    def show(self) -> None:
        self.visible = True
        self.frames = 0
        self._held_s = 0.0
        self.root.enabled = True
        logger.info("Intro card shown: %s", TITLE_TEXT)

    def hide(self) -> None:
        self.visible = False
        self.root.enabled = False

    def dismiss(self) -> None:
        """Drop the slate (click / key / programmatic). Idempotent:
        the on_dismiss callback fires exactly once per show."""
        if not self.visible:
            return
        self.hide()
        logger.info("Intro card dismissed after %.2fs / %d frames",
                    self._held_s, self.frames)
        self.on_dismiss()

    def tick(self, dt: float) -> bool:
        """Advance the slate. Returns True on the tick it auto-drops
        (after AUTO_HOLD_S) — a host that never dismisses it manually
        still flows into the take."""
        if not self.visible or dt <= 0:
            return False
        self.frames += 1
        self._held_s += dt
        if self._held_s >= AUTO_HOLD_S:
            self.dismiss()
            return True
        return False
