"""TimerManager — stage race timer for Action Star: NYC Siege 3D.

The Time-Attack metric is the acceptance test of the game: reach the end
of the stage as fast as possible. This module owns the stage clock, the
Base Time Bonus and the best-time record.

Rules (Cyrus's design):

* The timer counts UP from 0 against a stage time cap (the target time).
* ``remaining = max(0, cap - elapsed)``.
* Base Time Bonus (S_time) = ``max(0, (cap - elapsed) * 100)`` — every
  second left on the clock when the stage ends is worth 100 points, so
  S_time strictly decreases the longer the run takes and reaches 0 once
  the cap is passed (the run can still finish and earn its Stunt Score).
  (Formula approved by Cyrus 2026-10-27; full formula in take_rating.py.)
* Bullet Time does NOT stop or slow this timer. Bullet Time slows the
  world, not the audition clock — the Final Take Rating rewards real
  speed, so "pause/resume" here exists only for genuine game pauses
  (menus, cutscenes), never for Bullet Time.
* The best-time record is updated only when a finished run beats it.

Like StuntManager, time comes from an injected ``clock`` callable, so
tests are fully deterministic. No engine imports.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# S_time (Base Time Bonus) = TIME_BONUS_PER_SECOND x seconds remaining,
# floored at 0 — no base points (Cyrus's approved formula, 2026-10-27).
TIME_BONUS_PER_SECOND = 100


class TimerManager:
    """One stage's race timer.

    Parameters
    ----------
    clock:
        Zero-argument callable returning the current time in seconds.
    time_cap_seconds:
        The stage's time cap (the audition limit). Must be positive.
    """

    def __init__(self, clock: Callable[[], float], time_cap_seconds: float) -> None:
        if not callable(clock):
            raise TypeError("TimerManager requires a callable clock() -> float seconds")
        if isinstance(time_cap_seconds, bool) or not isinstance(
            time_cap_seconds, (int, float)
        ):
            raise TypeError("time_cap_seconds must be a number")
        if time_cap_seconds <= 0:
            raise ValueError("time_cap_seconds must be positive")
        self._clock = clock
        self.time_cap: float = float(time_cap_seconds)
        self.best_time: Optional[float] = None
        self._started_at: Optional[float] = None
        self._paused_total: float = 0.0
        self._pause_began_at: Optional[float] = None
        self._frozen_elapsed: Optional[float] = None

    # -------------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Start the stage clock. Raises RuntimeError if already started."""
        if self._started_at is not None:
            raise RuntimeError("TimerManager.start() called twice; call reset() first")
        self._started_at = float(self._clock())
        self._paused_total = 0.0
        self._pause_began_at = None
        self._frozen_elapsed = None
        logger.debug("Stage timer started (cap %.1fs)", self.time_cap)

    def pause(self) -> None:
        """Freeze the clock for a genuine game pause (menu/cutscene).

        NOT to be used for Bullet Time — Bullet Time never pauses the
        audition clock (see module docstring).
        """
        self._require_active("pause")
        if self._pause_began_at is not None:
            raise RuntimeError("TimerManager is already paused")
        self._pause_began_at = float(self._clock())

    def resume(self) -> None:
        """Resume after pause(); the paused span is excluded from elapsed."""
        self._require_active("resume")
        if self._pause_began_at is None:
            raise RuntimeError("TimerManager is not paused")
        now = float(self._clock())
        self._paused_total += now - self._pause_began_at
        self._pause_began_at = None

    def finish(self) -> float:
        """Stop the clock at stage end and settle the best-time record.

        Returns the final elapsed seconds. The best time is replaced only
        when this run is strictly faster. After finish(), ``elapsed`` stays
        frozen at the final value until ``reset()``.
        """
        self._require_active("finish")
        final = self.elapsed
        self._frozen_elapsed = final
        self._pause_began_at = None
        if self.best_time is None or final < self.best_time:
            self.best_time = final
            logger.info("New best time for the stage: %.2fs", final)
        return final

    def reset(self) -> None:
        """Clear the run state for a fresh attempt.

        ``best_time`` deliberately survives reset() — it is the stage
        record, not per-attempt state.
        """
        self._started_at = None
        self._paused_total = 0.0
        self._pause_began_at = None
        self._frozen_elapsed = None

    # ------------------------------------------------------------- properties

    @property
    def elapsed(self) -> float:
        """Seconds on the stage clock, excluding paused spans."""
        if self._frozen_elapsed is not None:
            return self._frozen_elapsed
        if self._started_at is None:
            return 0.0
        now = float(self._clock())
        paused = self._paused_total
        if self._pause_began_at is not None:
            paused += now - self._pause_began_at
        return max(0.0, now - self._started_at - paused)

    @property
    def remaining(self) -> float:
        """Seconds left before the cap; clamps at 0 once the cap is passed."""
        return max(0.0, self.time_cap - self.elapsed)

    @property
    def is_running(self) -> bool:
        """True after start() and before finish() (paused still counts)."""
        return self._started_at is not None and self._frozen_elapsed is None

    @property
    def is_paused(self) -> bool:
        return self._pause_began_at is not None

    # ---------------------------------------------------------------- scoring

    def time_bonus(self) -> int:
        """S_time = max(0, (T_target - T_actual) x 100).

        Sanity anchor: finishing in 85s against a 120s target leaves 35s,
        so S_time = 35 x 100 = 3500. Past the cap, S_time is 0. Uses the
        frozen elapsed after finish(), so the value quoted at the rating
        screen is exactly the value at the moment the run ended.
        """
        return int(self.remaining * TIME_BONUS_PER_SECOND)

    # -------------------------------------------------------------- internals

    def _require_active(self, what: str) -> None:
        if self._started_at is None:
            raise RuntimeError(f"TimerManager.{what}() called before start()")
        if self._frozen_elapsed is not None:
            raise RuntimeError(
                f"TimerManager.{what}() called after finish(); call reset() first"
            )
