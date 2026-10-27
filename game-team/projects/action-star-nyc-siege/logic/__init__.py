"""Engine-agnostic game-logic core for Action Star: NYC Siege 3D.

Three small, independently testable managers that together grade a run:

* :class:`StuntManager` — stunt points, variety combo multiplier,
  Multi-Kill Combo bonuses (the showmanship half).
* :class:`TimerManager` — stage race timer, Base Time Bonus and the
  best-time record (the speed half).
* :mod:`take_rating` — Final Take Rating: time bonus + stunt score ->
  S / A / B / C / F.

None of these modules import an engine (no pygame / ursina): the engine
layer feeds them events and reads their state for the HUD. All time comes
from injected clock callables, so behaviour is fully deterministic.
"""

from .stunt_manager import (
    KILL_ACTIONS,
    STUNT_MATRIX,
    MultiKillBonus,
    StuntEvent,
    StuntManager,
    multi_kill_band,
)
from .take_rating import RATING_TABLE, TakeResult, evaluate, rank_for_total, rate
from .timer_manager import TIME_BONUS_PER_SECOND, TimerManager

__all__ = [
    "KILL_ACTIONS",
    "STUNT_MATRIX",
    "MultiKillBonus",
    "StuntEvent",
    "StuntManager",
    "multi_kill_band",
    "RATING_TABLE",
    "TakeResult",
    "evaluate",
    "rank_for_total",
    "rate",
    "TIME_BONUS_PER_SECOND",
    "TimerManager",
]
