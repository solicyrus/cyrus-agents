"""TakeRating — Final Take Rating for Action Star: NYC Siege 3D.

Approved by Cyrus 2026-10-27 — the official Final Take Rating formula:

    S_time  = max(0, (T_target − T_actual) × 100)
    S_total = S_time + (S_stunt × M_combo)

Where the components come from:

* ``S_time`` — the time component: :meth:`TimerManager.time_bonus`
  (seconds left under the target, x100, never below 0).
* ``S_stunt`` — the RAW sum of stunt base points over the whole take
  (:attr:`StuntManager.raw_base_total`) — no multiplier baked in.
* ``M_combo`` — the combo multiplier the player holds at the end of the
  take (:attr:`StuntManager.combo_multiplier`). It applies to the stunt
  component ONLY, never to S_time: speed is graded raw, style is graded
  with its multiplier.

S_total is graded on Cyrus's official table, with cinematic titles:

    S  "Perfect Take"       >= 15,000
    A  "Box Office Hit"     >= 10,000
    B  "Good Take"          >=  6,000
    C  "Wrap Scene"         >=  3,000
    F  "Re-take Required"   <   3,000

Note on the live HUD score: StuntManager.current_score (per-event
multiplied points + Multi-Kill bonuses) is the in-game performance meter.
The Final Take Rating deliberately re-derives the stunt component from
the raw base sum and the final multiplier, exactly as the formula above
prescribes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Tuple

logger = logging.getLogger(__name__)

# Cyrus's official rating table: (rank, cinematic title, minimum S_total).
# Ordered best-first; a total reaching none of the thresholds is an F.
RATING_TABLE: Tuple[Tuple[str, str, int], ...] = (
    ("S", "Perfect Take", 15000),
    ("A", "Box Office Hit", 10000),
    ("B", "Good Take", 6000),
    ("C", "Wrap Scene", 3000),
)
FAIL_RANK = "F"
FAIL_TITLE = "Re-take Required"


@dataclass(frozen=True)
class TakeResult:
    """Full breakdown of one graded take (for the rating screen / logs)."""

    s_time: int
    stunt_base: int
    combo_multiplier: float
    stunt_component: int
    total: int
    rank: str
    title: str


def rank_for_total(total: int) -> Tuple[str, str]:
    """(rank, title) for a final S_total, per Cyrus's official table."""
    total = _validate_score(total, "total")
    for rank, title, threshold in RATING_TABLE:
        if total >= threshold:
            return rank, title
    return FAIL_RANK, FAIL_TITLE


def rate(s_time: int, s_stunt: int, m_combo: float) -> Tuple[int, str, str]:
    """Grade a take: returns (S_total, rank, title).

    S_total = S_time + int(S_stunt x M_combo) — the combo multiplier
    touches the stunt component only.
    """
    result = evaluate(s_time, s_stunt, m_combo)
    return result.total, result.rank, result.title


def evaluate(s_time: int, s_stunt: int, m_combo: float) -> TakeResult:
    """Grade a take and return the full TakeResult breakdown."""
    s_time = _validate_score(s_time, "s_time")
    s_stunt = _validate_score(s_stunt, "s_stunt")
    m_combo = _validate_multiplier(m_combo)
    stunt_component = int(s_stunt * m_combo)
    total = s_time + stunt_component
    rank, title = rank_for_total(total)
    logger.debug(
        "Take rated: s_time=%d stunt=%d x%.2f -> %d total=%d rank=%s (%s)",
        s_time, s_stunt, m_combo, stunt_component, total, rank, title,
    )
    return TakeResult(
        s_time=s_time,
        stunt_base=s_stunt,
        combo_multiplier=m_combo,
        stunt_component=stunt_component,
        total=total,
        rank=rank,
        title=title,
    )


def _validate_score(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


def _validate_multiplier(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"m_combo must be a number, got {type(value).__name__}"
        )
    if value <= 0:
        raise ValueError(f"m_combo must be > 0, got {value}")
    return float(value)
