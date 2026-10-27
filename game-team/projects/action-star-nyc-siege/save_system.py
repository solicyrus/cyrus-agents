"""SaveSystem — local progress store for Action Star: NYC Siege 3D.

Persists the player's tower progress to ``user_progress.json``:

  * ``unlocked_levels`` — which tower floors may be entered;
  * ``levels_data``     — per floor, the record of the BEST-scoring take
    (``best_score`` = that take's S_total; its ``best_time`` and
    ``best_rank`` travel with it — they describe the same run).

Semantics (Cyrus's approved design, kept exactly):

  * A fresh profile unlocks only Level 1.
  * ``save_stage_result`` replaces a floor's record ONLY when the new
    score beats the stored ``best_score``.
  * Finishing a floor with any rank other than "F" unlocks the next
    floor (there are exactly 3 floors; nothing unlocks past Level 3).

Where the file lives: a writable per-user directory —
``%APPDATA%/ActionStar/`` on Windows, ``~/.actionstar/`` elsewhere.
It is NEVER placed next to the code or inside a PyInstaller bundle:
``sys._MEIPASS`` is a read-only extraction directory, so a save file
written there would silently vanish (or fail) on the packaged game.
Pass ``save_path`` to the constructor to override (tests, portable
mode).

Writes are crash-safe: the JSON goes to a temp file in the same
directory and is then moved over the real file with ``os.replace``, so
a power cut mid-write can never leave a half-written save. A missing
or corrupt file loads as a fresh profile instead of crashing.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SAVE_FILENAME = "user_progress.json"

LEVEL_TITLES: Dict[int, str] = {
    1: "NYC Tower Lobby",
    2: "Data Center",
    3: "Penthouse & Helipad",
}
MAX_LEVEL = 3

#: Ranks a finished take can earn (from logic.take_rating).
PASSING_RANKS = ("S", "A", "B", "C")
ALL_RANKS = PASSING_RANKS + ("F",)
NO_RECORD_RANK = "N/A"


def default_save_path() -> str:
    """Absolute path of the save file in the per-user data directory."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, "ActionStar")
    else:
        folder = os.path.join(os.path.expanduser("~"), ".actionstar")
    return os.path.join(folder, SAVE_FILENAME)


def _default_record(level_num: int) -> dict:
    return {
        "title": LEVEL_TITLES[level_num],
        "best_score": 0,
        "best_time": 0.0,
        "best_rank": NO_RECORD_RANK,
    }


def _default_data() -> dict:
    return {
        "unlocked_levels": [1],
        "levels_data": {
            f"level_{n}": _default_record(n) for n in LEVEL_TITLES
        },
    }


def _clean_record(level_num: int, raw: object) -> dict:
    """Validate one level record from disk; fall back per-field."""
    record = _default_record(level_num)
    if not isinstance(raw, dict):
        return record
    title = raw.get("title")
    if isinstance(title, str) and title:
        record["title"] = title
    score = raw.get("best_score")
    if isinstance(score, (int, float)) and not isinstance(score, bool) \
            and score >= 0:
        record["best_score"] = int(score)
    time_taken = raw.get("best_time")
    if isinstance(time_taken, (int, float)) \
            and not isinstance(time_taken, bool) and time_taken >= 0:
        record["best_time"] = float(time_taken)
    rank = raw.get("best_rank")
    if rank in ALL_RANKS or rank == NO_RECORD_RANK:
        record["best_rank"] = rank
    return record


def _clean_data(raw: object) -> dict:
    """Validate a whole save payload; unknown keys are tolerated."""
    data = _default_data()
    if not isinstance(raw, dict):
        return data
    unlocked = raw.get("unlocked_levels")
    if isinstance(unlocked, list):
        valid = sorted({
            n for n in unlocked
            if isinstance(n, int) and not isinstance(n, bool)
            and n in LEVEL_TITLES
        })
        if valid:
            data["unlocked_levels"] = valid
    if 1 not in data["unlocked_levels"]:
        data["unlocked_levels"] = sorted(data["unlocked_levels"] + [1])
    levels_data = raw.get("levels_data")
    if isinstance(levels_data, dict):
        for n in LEVEL_TITLES:
            key = f"level_{n}"
            if key in levels_data:
                data["levels_data"][key] = _clean_record(
                    n, levels_data[key])
    return data


class SaveManager:
    """Reads, writes and answers questions about ``user_progress.json``.

    One instance is shared by the main menu, the level-select screen
    and the game pipeline: the pipeline calls :meth:`save_stage_result`
    at the end of every floor; the menus read through
    :meth:`is_unlocked` / :meth:`get_level_record`.
    """

    #: File name used inside the per-user directory (Cyrus's original).
    SAVE_FILE = SAVE_FILENAME

    def __init__(self, save_path: Optional[str] = None) -> None:
        self.save_path = save_path or default_save_path()
        self.data = self.load_data()

    # ------------------------------------------------------------ loading
    def load_data(self) -> dict:
        """Load and validate the save file; defaults when unusable."""
        if not os.path.exists(self.save_path):
            logger.info("SaveSystem: no save file at %s — fresh profile",
                        self.save_path)
            return _default_data()
        try:
            with open(self.save_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            logger.warning(
                "SaveSystem: save file %s unreadable (%s) — fresh profile",
                self.save_path, exc)
            return _default_data()
        return _clean_data(raw)

    # ------------------------------------------------------------ queries
    @property
    def unlocked_levels(self) -> List[int]:
        """Sorted list of unlocked level numbers (a copy)."""
        return sorted(self.data["unlocked_levels"])

    def is_unlocked(self, level_num: int) -> bool:
        """True when ``level_num`` may be entered from level select."""
        if level_num not in LEVEL_TITLES:
            return False
        return level_num in self.data["unlocked_levels"]

    def get_level_record(self, level_num: int) -> dict:
        """A copy of one floor's record (title/best_score/best_time/rank)."""
        if level_num not in LEVEL_TITLES:
            raise ValueError(f"unknown level number: {level_num!r}")
        return dict(self.data["levels_data"][f"level_{level_num}"])

    # ------------------------------------------------------------ writing
    def save_stage_result(self, level_num: int, score: int,
                          time_taken: float, rank: str) -> bool:
        """Record a finished take; unlock the next floor on a pass.

        The floor's record is replaced ONLY when ``score`` beats the
        stored best score — the stored time and rank always describe
        that same best-scoring take. Any rank other than "F" unlocks
        floor ``level_num + 1`` (never past Level 3).

        Returns True when the record was improved.
        """
        if level_num not in LEVEL_TITLES:
            raise ValueError(f"unknown level number: {level_num!r}")
        if rank not in ALL_RANKS:
            raise ValueError(f"unknown rank: {rank!r}")
        score = int(score)
        time_taken = float(time_taken)
        if score < 0 or time_taken < 0:
            raise ValueError("score and time_taken must be >= 0")

        key = f"level_{level_num}"
        current = self.data["levels_data"][key]
        improved = score > current["best_score"]
        if improved:
            self.data["levels_data"][key] = {
                "title": current["title"],
                "best_score": score,
                "best_time": time_taken,
                "best_rank": rank,
            }
            logger.info(
                "SaveSystem: new record on level %d — %d pts, %.1fs, "
                "rank %s", level_num, score, time_taken, rank)

        next_level = level_num + 1
        if rank != "F" and next_level <= MAX_LEVEL \
                and next_level not in self.data["unlocked_levels"]:
            self.data["unlocked_levels"].append(next_level)
            self.data["unlocked_levels"].sort()
            logger.info("SaveSystem: level %d unlocked", next_level)

        self._persist()
        return improved

    def _persist(self) -> None:
        """Crash-safe write: temp file in the same dir + os.replace."""
        folder = os.path.dirname(os.path.abspath(self.save_path))
        try:
            os.makedirs(folder, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=folder, prefix=".user_progress-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(self.data, handle, indent=4)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_path, self.save_path)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            logger.error("SaveSystem: could not write %s (%s)",
                         self.save_path, exc)
            raise
