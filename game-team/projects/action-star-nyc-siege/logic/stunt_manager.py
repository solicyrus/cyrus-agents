"""StuntManager — Stunt Score & Combo system for Action Star: NYC Siege 3D.

Design owner: Cyrus (studio boss). The game is not a plain speedrun: the
actor is graded like a Hollywood stunt performer — speed matters (see
TimerManager), but so does showmanship. This module owns the showmanship
half: stunt points, the variety (combo) multiplier, and Multi-Kill Combos.

Core semantics (Cyrus's own design, implemented faithfully):

* Every stunt action has base points from the Stunt Matrix below.
* ``register_stunt(action_type, points)``: if the action is NOT one of the
  last 3 registered actions, the combo multiplier grows by +0.5 (variety is
  rewarded), capped at x5.0. Awarded points = ``int(points * multiplier)``.
  Repeating the same moves does not grow the multiplier.
* ``reset_combo()`` is called when the player takes a hit: the multiplier
  collapses back to x1.0. Banked score is never taken away.
* Multi-Kill Combo: kills are timestamped. Whenever a kill lands, the kills
  inside the trailing 2.0-second window set a bonus band — 3 kills -> x2,
  4 kills -> x3, 5+ kills -> x5 — applied to the points those kills scored.
  The bonus ESCALATES: if more kills land inside the same window and the
  band rises, only the unpaid difference is added (no double payment), and
  a later, separate cluster of kills earns its own bonus. This is the only
  reading under which the x3/x5 bands are reachable at all: paying once at
  the 3rd kill and consuming the kills would freeze every window at x2.
  Kills already counted keep their paid band even after they slide out of
  the window, so a kill can never be paid twice.

Determinism: the manager never reads the wall clock. Every event takes its
timestamp from the injected ``clock`` callable, or from an explicit
``timestamp=`` argument — tests drive it with a fake clock and get exact,
reproducible numbers.

Engine-agnostic: no pygame / ursina imports. The engine layer translates
game events (a dodge in Bullet Time, a slide-shot kill, ...) into
``register(...)`` calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Stunt Matrix (Cyrus's table): base points per action -------------------
STUNT_MATRIX: Dict[str, int] = {
    "bullet_dodge": 50,     # dodge a bullet while in Bullet Time
    "slide_shoot": 100,     # shoot & kill an enemy while sliding (takedown slide)
    "air_takedown": 150,    # melee takedown throwing an enemy from window/height
    "wall_run_kill": 200,   # shoot & kill an enemy while wall-running
}

# Actions that count as enemy kills for Multi-Kill Combo tracking.
KILL_ACTIONS = frozenset({"slide_shoot", "air_takedown", "wall_run_kill"})

# --- Combo / variety tuning --------------------------------------------------
DIVERSITY_WINDOW = 3        # the action must be absent from the last N actions
DIVERSITY_STEP = 0.5        # multiplier growth per *new* action type
MAX_MULTIPLIER = 5.0        # hard cap on the variety multiplier

# --- Multi-Kill Combo tuning --------------------------------------------------
MULTI_KILL_WINDOW_S = 2.0   # kills inside this trailing window form a cluster
MULTI_KILL_MIN_KILLS = 3    # a cluster needs at least this many kills


def multi_kill_band(kills_in_window: int) -> float:
    """Bonus band for a Multi-Kill Combo, scaled by kills inside the window.

    Band table (Cyrus's x2–x5 range):
        3 kills -> x2 | 4 kills -> x3 | 5 or more kills -> x5
    Fewer than 3 kills is not a combo and returns x1.0 (no bonus).
    """
    if kills_in_window >= 5:
        return 5.0
    if kills_in_window == 4:
        return 3.0
    if kills_in_window == 3:
        return 2.0
    return 1.0


@dataclass
class StuntEvent:
    """One registered stunt, exactly as it was scored."""

    action_type: str
    base_points: int
    multiplier_applied: float
    points_awarded: int
    timestamp: float
    is_kill: bool


@dataclass
class MultiKillBonus:
    """One Multi-Kill Combo payment (an escalation step counts as a payment)."""

    kills_in_window: int
    band: float
    bonus_points: int
    triggered_at: float


@dataclass
class _KillRecord:
    """A kill kept for window/band bookkeeping. ``paid_band`` is the highest
    band this kill's points have already been bonused at (1.0 = unpaid)."""

    seq: int
    timestamp: float
    points: int
    paid_band: float = 1.0


class StuntManager:
    """Tracks Stunt Score, the variety combo multiplier and Multi-Kill Combos.

    Parameters
    ----------
    clock:
        Zero-argument callable returning the current game time in seconds
        (float). Injected so the engine controls time (Bullet Time, pauses)
        and tests stay deterministic.
    """

    def __init__(self, clock: Callable[[], float]) -> None:
        if not callable(clock):
            raise TypeError("StuntManager requires a callable clock() -> float seconds")
        self._clock = clock
        self.current_score: int = 0
        self.combo_multiplier: float = 1.0
        self.recent_actions: List[str] = []
        self.events: List[StuntEvent] = []
        self.multi_kill_bonuses: List[MultiKillBonus] = []
        self._kills: List[_KillRecord] = []
        self._kill_seq = 0

    # ------------------------------------------------------------------ API

    def register(
        self,
        action_type: str,
        points: Optional[int] = None,
        timestamp: Optional[float] = None,
    ) -> Tuple[int, float]:
        """Register a stunt by name.

        Base points come from the Stunt Matrix unless ``points`` overrides
        them (an override also permits action names outside the matrix, for
        future moves). Returns ``(points_added, current_multiplier)`` where
        ``points_added`` includes any Multi-Kill Combo bonus this event
        triggered. Raises ValueError for an unknown action without points.
        """
        self._validate_action_type(action_type)
        if points is None:
            if action_type not in STUNT_MATRIX:
                raise ValueError(
                    f"Unknown stunt action {action_type!r} and no points override; "
                    f"known actions: {sorted(STUNT_MATRIX)}"
                )
            base_points = STUNT_MATRIX[action_type]
        else:
            base_points = self._validate_points(points)
        return self.register_stunt(action_type, base_points, timestamp=timestamp)

    def register_stunt(
        self,
        action_type: str,
        points: int,
        timestamp: Optional[float] = None,
    ) -> Tuple[int, float]:
        """Register a stunt with explicit base points (Cyrus's core method).

        Variety rule: a genuinely new action (absent from the last
        ``DIVERSITY_WINDOW`` actions) raises the combo multiplier by
        ``DIVERSITY_STEP`` up to ``MAX_MULTIPLIER`` *before* scoring, so the
        new move itself already benefits from the raise — exactly as in
        Cyrus's reference implementation.
        """
        self._validate_action_type(action_type)
        base_points = self._validate_points(points)
        ts = self._resolve_timestamp(timestamp)

        if action_type not in self.recent_actions[-DIVERSITY_WINDOW:]:
            self.combo_multiplier = min(
                self.combo_multiplier + DIVERSITY_STEP, MAX_MULTIPLIER
            )

        added = int(base_points * self.combo_multiplier)
        self.current_score += added
        self.recent_actions.append(action_type)
        is_kill = action_type in KILL_ACTIONS
        self.events.append(
            StuntEvent(
                action_type=action_type,
                base_points=base_points,
                multiplier_applied=self.combo_multiplier,
                points_awarded=added,
                timestamp=ts,
                is_kill=is_kill,
            )
        )
        logger.debug(
            "stunt %s base=%d x%.1f -> +%d (score=%d)",
            action_type, base_points, self.combo_multiplier, added, self.current_score,
        )

        total_added = added
        if is_kill:
            total_added += self._track_kill(ts, added)
        return total_added, self.combo_multiplier

    @property
    def raw_base_total(self) -> int:
        """S_stunt input of the Final Take Rating: the RAW sum of base
        points over every registered stunt — no multiplier, no Multi-Kill
        bonus baked in. (The rating formula applies the final combo
        multiplier to this sum; see take_rating.py.)"""
        return sum(event.base_points for event in self.events)

    def reset_combo(self) -> None:
        """Player took a hit: multiplier collapses to x1.0.

        The banked score and the action history are kept (variety is judged
        on what the player actually did), and kill-window bookkeeping is
        untouched — a hit does not rewrite kill history.
        """
        self.combo_multiplier = 1.0
        logger.info("Combo reset by player hit: multiplier back to x1.0")

    # ------------------------------------------------------------- internals

    def _track_kill(self, ts: float, points_attributed: int) -> int:
        """Record a kill and pay any Multi-Kill Combo bonus it triggers.

        Returns the bonus points paid by this event (0 when no band rise).
        Escalation rule: the trailing window's band is recomputed on every
        kill; each kill in the window is entitled to
        ``points * (band - 1)`` total bonus, and only the part not already
        paid (``band - paid_band``) is paid now.
        """
        self._kill_seq += 1
        record = _KillRecord(seq=self._kill_seq, timestamp=ts, points=points_attributed)
        self._kills.append(record)

        window = [
            k for k in self._kills
            if ts - MULTI_KILL_WINDOW_S <= k.timestamp <= ts
        ]
        if len(window) < MULTI_KILL_MIN_KILLS:
            return 0
        band = multi_kill_band(len(window))
        if band <= 1.0:
            return 0

        delta = 0
        for kill in window:
            if band > kill.paid_band:
                delta += int(kill.points * (band - kill.paid_band))
                kill.paid_band = band
        if delta <= 0:
            return 0

        self.current_score += delta
        self.multi_kill_bonuses.append(
            MultiKillBonus(
                kills_in_window=len(window),
                band=band,
                bonus_points=delta,
                triggered_at=ts,
            )
        )
        logger.info(
            "Multi-Kill Combo x%.1f (%d kills in %.1fs window): +%d bonus points",
            band, len(window), MULTI_KILL_WINDOW_S, delta,
        )
        return delta

    def _resolve_timestamp(self, timestamp: Optional[float]) -> float:
        if timestamp is None:
            return float(self._clock())
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise TypeError("timestamp must be a number of seconds (int or float)")
        return float(timestamp)

    @staticmethod
    def _validate_action_type(action_type: object) -> None:
        if not isinstance(action_type, str) or not action_type:
            raise ValueError("action_type must be a non-empty string")

    @staticmethod
    def _validate_points(points: object) -> int:
        if isinstance(points, bool) or not isinstance(points, int):
            raise TypeError("points must be an int")
        if points < 0:
            raise ValueError("points must be >= 0")
        return points
