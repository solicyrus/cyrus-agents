"""pipeline_state — the chain state of a full Action Star run.

Support module for full_game_pipeline.py. This module owns everything
that makes three separate floors ONE run (Cyrus's integration rules,
2026-10-27) — and nothing else: no engine imports, no scene code, so
the chain math is unit-testable with fake clocks.

THE CHAIN RULES (also documented in full_game_pipeline.py):

1. ONE StuntManager lives across all three floors. Its current_score,
   combo_multiplier, recent-action chain, event history and raw base
   total are NEVER reset between floors. (Player hits still call
   reset_combo() — that is a StuntManager rule, not a floor change.)
   The manager's clock is bound to whichever floor timer is active, so
   Multi-Kill windows are measured on the current floor's race clock —
   the same binding level1/main.py uses inside one floor.

2. TIME BANKING: each floor's TimerManager cap (its effective target)
   = the floor's base target + the seconds banked from the previous
   floor, where banked = max(0, previous effective target − previous
   actual time) — i.e. TimerManager.remaining at the moment the floor
   ended. Banked seconds are spent into the next floor's cap only;
   unspent banked seconds bank AGAIN (each floor's remaining is
   computed against its effective cap, so accrual is uncapped).
   APPLIED-BONUS CAP (Cyrus's order, 2026-10-27): the bonus actually
   applied to a floor's target is capped at +30 s —
   effective_target = base_target + min(banked_seconds, 30.0).
   Only the applied bonus is capped; the accrued bank itself is not.

3. HEAL BY RANK (v1 table — Cyrus's rule "heal based on rank"; the
   numbers are v1 and marked as such so they can be re-tuned):
       S -> restore to 100% HP
       A -> +60 HP      B -> +40 HP      C -> +25 HP   (cap 100)
   The heal is computed from the FLOOR's own take rating (the floor's
   S_time + the stunt base gained ON THAT FLOOR, at the combo held at
   floor end — the same evaluate() inputs level1 uses for one take).
   A floor rated F is a FAILED TAKE: no heal, no banking, and the
   chain stops for a Re-take (no advance to the next floor). A floor
   that is lost outright (player down / time out) is likewise rated F,
   exactly as level1/main.py forces F on a lost take.

4. FINAL CARD aggregation: the whole run is graded by
   logic/take_rating.py as
       S_total = SUM(floor S_time) + (total raw stunt base x final combo)
   where "total raw stunt base" is the shared StuntManager's
   raw_base_total over ALL floors and "final combo" is the multiplier
   held when the last floor ended. On a failed chain the numeric total
   is still reported, but rank/title are forced to F / "Re-take
   Required" (the level1 convention).

SaveManager seam: SaveBridge below is the pipeline's only contact with
save_system.py (project root, owned by the save-system workstream).
Specified interface (2026-10-27):
    SaveManager().save_stage_result(level_num, score, time_taken, rank)
    SaveManager().is_unlocked(level_num) -> bool
If the module has not landed yet, the bridge records every call it
WOULD have made (delivered=False) and says so — it never fakes a save.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from logic import take_rating
from logic.stunt_manager import StuntManager
from logic.timer_manager import TimerManager

logger = logging.getLogger(__name__)

# The tower (Cyrus 2026-10-27): level number, phase4 stage id, display
# name, base target seconds. Stage ids/targets match
# phase4.game_settings.STAGES exactly.
FLOOR_TABLE = (
    (1, "lobby", "Lobby", 90.0),
    (2, "data_center", "Data Center", 75.0),
    (3, "penthouse", "Penthouse", 105.0),
)
FLOORS_BY_NUMBER = {row[0]: row for row in FLOOR_TABLE}
MAX_HP = 100.0

# Applied time-bank bonus cap (Cyrus's order, 2026-10-27): no floor's
# target grows by more than this many banked seconds, however large
# the accrued bank is. See module docstring, chain rule 2.
BANK_BONUS_CAP_S = 30.0

# Heal-by-rank v1 table (see module docstring, rule 3). S is a full
# restore and is handled separately in heal_for_rank().
HEAL_BY_RANK_V1 = {"A": 60.0, "B": 40.0, "C": 25.0, "F": 0.0}
HEAL_TABLE_VERSION = "v1"


def heal_for_rank(rank: str, hp_now: float,
                  max_hp: float = MAX_HP) -> tuple:
    """(hp_after, heal_applied) for a floor rated `rank`, v1 table."""
    if rank == "S":
        target = float(max_hp)
    elif rank in HEAL_BY_RANK_V1:
        target = min(float(max_hp), float(hp_now) + HEAL_BY_RANK_V1[rank])
    else:
        raise ValueError(f"unknown rank {rank!r}")
    target = max(float(hp_now), target) if rank != "F" else float(hp_now)
    if rank == "F":
        return float(hp_now), 0.0
    return target, target - float(hp_now)


@dataclass
class FloorRecord:
    """One settled floor of the chain — the elevator panel's data, the
    chain log's rows, and the final card's building blocks."""

    level_num: int
    stage_id: str
    stage_name: str
    base_target_s: float
    banked_in_s: float
    effective_target_s: float
    t_actual_s: float
    s_time: int
    stunt_base_start: int
    stunt_base_end: int
    stunt_base_gained: int
    stunt_score_end: int          # live HUD score (multiplied) at floor end
    combo_end: float
    floor_s_total: int            # this floor's own take total
    floor_rank: str
    floor_title: str
    outcome: str                  # "WIN" | "FAILED"
    reason: str
    hp_start: float
    hp_end_pre_heal: float
    heal_applied: float
    hp_after_heal: float
    banked_out_s: float
    boss_defeated: Optional[bool] = None
    save_call: Optional[dict] = None

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class RunState:
    """The persistent run: shared StuntManager, HP, banked time,
    floor records. Created once per run (a level-select entry at
    floor N > 1 creates a FRESH RunState — fresh manager, full HP,
    no bank — per Cyrus's integration note)."""

    def __init__(self, start_floor: int = 1) -> None:
        if start_floor not in FLOORS_BY_NUMBER:
            raise ValueError(f"start_floor must be one of "
                             f"{sorted(FLOORS_BY_NUMBER)}, got {start_floor}")
        self.start_floor = start_floor
        self.hp: float = MAX_HP
        self.banked_seconds: float = 0.0
        self.floor_records: List[FloorRecord] = []
        self.combo_peak: float = 1.0
        self.chain_failed: bool = False
        self.failed_at_floor: Optional[int] = None
        self._active_timer: Optional[TimerManager] = None
        # The ONE StuntManager of the run. Its clock reads the active
        # floor timer (chain rule 1).
        self.stunt = StuntManager(clock=self._stunt_clock)

    # ------------------------------------------------------------ clock
    def _stunt_clock(self) -> float:
        timer = self._active_timer
        return timer.elapsed if timer is not None else 0.0

    def attach_timer(self, timer: TimerManager) -> None:
        """Bind the shared StuntManager's clock to a floor's timer."""
        self._active_timer = timer

    def observe_combo(self) -> None:
        """Track the run's peak combo (VictoryScreen run_record field)."""
        if self.stunt.combo_multiplier > self.combo_peak:
            self.combo_peak = self.stunt.combo_multiplier

    # ------------------------------------------------------------- math
    def effective_target(self, base_target_s: float) -> float:
        """Chain rule 2: base target + banked seconds, with the
        applied bonus capped at +BANK_BONUS_CAP_S (30 s)."""
        return float(base_target_s) + min(self.banked_seconds,
                                          BANK_BONUS_CAP_S)

    def settle_floor(self, *, level_num: int, timer: TimerManager,
                     won: bool, reason: str, hp_end_pre_heal: float,
                     stunt_base_start: int,
                     boss_defeated: Optional[bool] = None) -> FloorRecord:
        """Settle one finished floor: rate its take, heal, bank, and
        decide whether the chain advances. The floor's TimerManager
        must already be finish()ed (frozen) by the session.

        Returns the FloorRecord (also appended to floor_records).
        Mutates self.hp / self.banked_seconds ONLY when the chain
        advances (won AND rated above F).
        """
        _num, stage_id, stage_name, base_target = FLOORS_BY_NUMBER[level_num]
        t_actual = timer.elapsed
        s_time = timer.time_bonus()
        banked_out = timer.remaining
        stunt_base_end = self.stunt.raw_base_total
        stunt_gained = stunt_base_end - stunt_base_start
        evaluated = take_rating.evaluate(
            s_time, stunt_gained, self.stunt.combo_multiplier)
        if won:
            rank, title = evaluated.rank, evaluated.title
        else:
            rank, title = take_rating.FAIL_RANK, take_rating.FAIL_TITLE
        advances = bool(won) and rank != take_rating.FAIL_RANK
        hp_start = self.hp
        if advances:
            hp_after, heal = heal_for_rank(rank, hp_end_pre_heal)
            self.hp = hp_after
            self.banked_seconds = banked_out
        else:
            heal = 0.0
            hp_after = float(hp_end_pre_heal)
            self.chain_failed = True
            self.failed_at_floor = level_num
        record = FloorRecord(
            level_num=level_num,
            stage_id=stage_id,
            stage_name=stage_name,
            base_target_s=float(base_target),
            banked_in_s=round(float(timer.time_cap) - float(base_target), 2),
            effective_target_s=float(timer.time_cap),
            t_actual_s=round(float(t_actual), 2),
            s_time=int(s_time),
            stunt_base_start=int(stunt_base_start),
            stunt_base_end=int(stunt_base_end),
            stunt_base_gained=int(stunt_gained),
            stunt_score_end=int(self.stunt.current_score),
            combo_end=float(self.stunt.combo_multiplier),
            floor_s_total=int(evaluated.total),
            floor_rank=rank,
            floor_title=title,
            outcome="WIN" if won else "FAILED",
            reason=reason,
            hp_start=round(float(hp_start), 1),
            hp_end_pre_heal=round(float(hp_end_pre_heal), 1),
            heal_applied=round(float(heal), 1),
            hp_after_heal=round(float(hp_after), 1),
            banked_out_s=round(float(banked_out), 2),
            boss_defeated=boss_defeated,
        )
        self.floor_records.append(record)
        logger.info(
            "Floor %d settled: %s rank %s total %d (s_time %d, stunt +%d) "
            "heal +%.0f banked %.1fs advance=%s",
            level_num, record.outcome, rank, record.floor_s_total,
            record.s_time, record.stunt_base_gained, record.heal_applied,
            record.banked_out_s, advances)
        return record

    def final_evaluation(self) -> tuple:
        """Chain rule 4: (TakeResult, total_s_time) for the whole run.

        S_total = SUM(floor S_time) + (total raw stunt base x final
        combo), computed BY take_rating.evaluate so the final card can
        never drift from the studio's rating code.
        """
        total_s_time = sum(r.s_time for r in self.floor_records)
        result = take_rating.evaluate(
            total_s_time,
            self.stunt.raw_base_total,
            self.stunt.combo_multiplier,
        )
        return result, total_s_time


class SaveBridge:
    """The pipeline's only contact with save_system.SaveManager.

    Specified interface (save-system workstream, 2026-10-27):
        SaveManager().save_stage_result(level_num, score, time_taken, rank)
        SaveManager().is_unlocked(level_num) -> bool

    If save_system.py has not landed, ``present`` is False, the import
    error is kept, and every call is recorded with delivered=False —
    the wiring is exercised and auditable, the save is NEVER faked.
    """

    def __init__(self) -> None:
        self.present: bool = False
        self.manager = None
        self.import_error: Optional[str] = None
        self.calls: List[dict] = []
        try:
            from save_system import SaveManager
            self.manager = SaveManager()
            self.present = True
            logger.info("SaveBridge: save_system.SaveManager connected")
        except Exception as exc:  # module not landed / interface drift
            self.import_error = f"{type(exc).__name__}: {exc}"
            logger.warning("SaveBridge: save_system unavailable (%s) — "
                           "saves will be logged as not delivered",
                           self.import_error)

    def save_floor_result(self, level_num: int, score: int,
                          time_taken: float, rank: str) -> dict:
        """Call save_stage_result for one settled floor (or record the
        attempt). Returns the call record stored on the FloorRecord."""
        call = {
            "method": "save_stage_result",
            "level_num": int(level_num),
            "score": int(score),
            "time_taken": float(time_taken),
            "rank": str(rank),
            "delivered": bool(self.present),
        }
        self.calls.append(call)
        if self.present:
            self.manager.save_stage_result(
                call["level_num"], call["score"],
                call["time_taken"], call["rank"])
            logger.info("Saved floor %d result via SaveManager", level_num)
        return call

    def is_unlocked(self, level_num: int) -> Optional[bool]:
        """True/False from the real SaveManager; None when the save
        system is absent (the caller decides — dev/test entry is not
        blocked by a missing persistence module, and says so)."""
        if not self.present:
            return None
        return bool(self.manager.is_unlocked(int(level_num)))
