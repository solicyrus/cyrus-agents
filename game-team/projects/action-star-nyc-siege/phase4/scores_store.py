"""High-scores store for Action Star: NYC Siege 3D.

Persists the best graded take per stage to ``high_scores.json`` in the
user-data folder (see assets.user_data_path — deliberately NOT inside
the app bundle, which is read-only/temporary when frozen).

One record per stage id:
    {s_total, rank, title, s_time, stunt_base, combo_multiplier,
     t_actual, t_target, recorded_at}
A new take replaces the stored one only when its S_total is higher —
the store is a *best* table, not a history log.
"""

from __future__ import annotations

import json
import logging
import time as _time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from phase4.assets import user_data_path

logger = logging.getLogger(__name__)

STORE_FILENAME = "high_scores.json"

# Stage registry: id -> (display name, target time in seconds).
STAGES: Dict[str, tuple] = {
    "lobby": ("Lobby", 90.0),
    "data_center": ("Data Center", 75.0),
    "penthouse": ("Penthouse", 105.0),
}


@dataclass(frozen=True)
class StageBest:
    stage_id: str
    s_total: int
    rank: str
    title: str
    s_time: int
    stunt_base: int
    combo_multiplier: float
    t_actual: float
    t_target: float
    recorded_at: float

    def to_dict(self) -> dict:
        return {
            "s_total": self.s_total, "rank": self.rank, "title": self.title,
            "s_time": self.s_time, "stunt_base": self.stunt_base,
            "combo_multiplier": self.combo_multiplier,
            "t_actual": self.t_actual, "t_target": self.t_target,
            "recorded_at": self.recorded_at,
        }

    @staticmethod
    def from_dict(stage_id: str, data: dict) -> "StageBest":
        return StageBest(
            stage_id=stage_id,
            s_total=int(data["s_total"]), rank=str(data["rank"]),
            title=str(data["title"]), s_time=int(data["s_time"]),
            stunt_base=int(data["stunt_base"]),
            combo_multiplier=float(data["combo_multiplier"]),
            t_actual=float(data["t_actual"]),
            t_target=float(data["t_target"]),
            recorded_at=float(data.get("recorded_at", 0.0)),
        )


class ScoresStore:
    """Load/save the per-stage best table. Safe on a missing/corrupt file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None \
            else user_data_path(STORE_FILENAME)
        self._bests: Dict[str, StageBest] = {}
        self.load()

    # -------------------------------------------------------------- io
    def load(self) -> None:
        self._bests = {}
        if not self.path.exists():
            logger.info("Scores store: no file yet at %s", self.path)
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for stage_id, data in raw.get("stages", {}).items():
                if stage_id in STAGES:
                    self._bests[stage_id] = StageBest.from_dict(stage_id, data)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Scores store unreadable (%s) — starting empty",
                           exc)
            self._bests = {}

    def save(self) -> None:
        payload = {
            "version": 1,
            "stages": {sid: best.to_dict()
                       for sid, best in sorted(self._bests.items())},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # atomic-ish: never leave a half-written file
        logger.info("Scores store saved to %s", self.path)

    # -------------------------------------------------------------- api
    def best(self, stage_id: str) -> Optional[StageBest]:
        return self._bests.get(stage_id)

    def all_bests(self) -> Dict[str, Optional[StageBest]]:
        """Every known stage -> its best (or None when no take recorded)."""
        return {sid: self._bests.get(sid) for sid in STAGES}

    def record(self, stage_id: str, *, s_total: int, rank: str, title: str,
               s_time: int, stunt_base: int, combo_multiplier: float,
               t_actual: float, t_target: float) -> bool:
        """Record a graded take. Returns True when it is the new best."""
        if stage_id not in STAGES:
            raise ValueError(f"unknown stage {stage_id!r}")
        current = self._bests.get(stage_id)
        if current is not None and s_total <= current.s_total:
            return False
        self._bests[stage_id] = StageBest(
            stage_id=stage_id, s_total=int(s_total), rank=rank, title=title,
            s_time=int(s_time), stunt_base=int(stunt_base),
            combo_multiplier=float(combo_multiplier),
            t_actual=float(t_actual), t_target=float(t_target),
            recorded_at=_time.time(),
        )
        self.save()
        return True
