"""Scores store QA — write -> read round-trip must preserve every value.

Run:  python test_scores_store.py   (exit 0 = all checks passed)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase4.scores_store import STAGES, ScoresStore  # noqa: E402

failures = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}  {detail}")
    if not ok:
        failures.append(label)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "high_scores.json"
        store = ScoresStore(path)
        check(store.best("lobby") is None, "empty store: lobby best is None")
        check(set(store.all_bests()) == set(STAGES),
              "all_bests covers all 3 stages")

        became = store.record(
            "lobby", s_total=11800, rank="A", title="Box Office Hit",
            s_time=3500, stunt_base=3320, combo_multiplier=2.5,
            t_actual=85.0, t_target=90.0)
        check(became, "first lobby take becomes best")

        reloaded = ScoresStore(path)   # fresh instance reads from disk
        best = reloaded.best("lobby")
        check(best is not None and best.s_total == 11800
              and best.rank == "A" and best.title == "Box Office Hit"
              and best.s_time == 3500 and best.stunt_base == 3320
              and abs(best.combo_multiplier - 2.5) < 1e-9
              and abs(best.t_actual - 85.0) < 1e-9
              and abs(best.t_target - 90.0) < 1e-9,
              "round-trip: every field survives write -> read",
              f"got {best}")

        worse = reloaded.record(
            "lobby", s_total=5000, rank="C", title="Wrap Scene",
            s_time=1000, stunt_base=1600, combo_multiplier=2.5,
            t_actual=88.0, t_target=90.0)
        check(not worse and ScoresStore(path).best("lobby").s_total == 11800,
              "lower take does NOT replace the best")

        better = reloaded.record(
            "lobby", s_total=15100, rank="S", title="Perfect Take",
            s_time=4100, stunt_base=4400, combo_multiplier=2.5,
            t_actual=86.0, t_target=90.0)
        check(better and ScoresStore(path).best("lobby").rank == "S",
              "higher take replaces the best")

        try:
            reloaded.record("rooftop", s_total=1, rank="F",
                            title="Re-take Required", s_time=0,
                            stunt_base=0, combo_multiplier=1.0,
                            t_actual=0.0, t_target=90.0)
            check(False, "unknown stage raises ValueError")
        except ValueError:
            check(True, "unknown stage raises ValueError")

    print(f"\n{'ALL PASS' if not failures else 'FAILURES: ' + str(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
