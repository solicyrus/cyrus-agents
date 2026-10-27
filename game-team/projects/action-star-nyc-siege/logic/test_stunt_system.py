#!/usr/bin/env python3
"""Deterministic QA checks for the Action Star: NYC Siege 3D logic core.

Simulates stunt/timer event streams against fake clocks and asserts the
exact numbers Cyrus's design implies — Stunt Matrix points, the variety
(diversity) multiplier rules, combo reset, Multi-Kill Combo windows and
escalating bands, the Base Time Bonus curve, best-time records, the Final
Take Rating thresholds, and stunt+timer running simultaneously without
interference.

Run:  python3 logic/test_stunt_system.py
Exit code 0 = every check passed; 1 = at least one failure.
No randomness, no wall clock, no engine imports.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic.stunt_manager import STUNT_MATRIX, StuntManager, multi_kill_band
from logic.take_rating import evaluate, rank_for_total, rate
from logic.timer_manager import TimerManager

RESULTS = []


def check(name, condition, detail=""):
    ok = bool(condition)
    RESULTS.append((name, ok))
    line = f"[{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def check_raises(name, exc_type, fn):
    try:
        fn()
    except exc_type:
        return check(name, True)
    except Exception as exc:  # noqa: BLE001 - report the wrong exception type
        return check(
            name, False,
            f"raised {type(exc).__name__} instead of {exc_type.__name__}: {exc}",
        )
    return check(name, False, "no exception raised")


class FakeClock:
    """Manually advanced clock: callable returning the current fake time."""

    def __init__(self, start=0.0):
        self.now = float(start)

    def __call__(self):
        return self.now

    def advance(self, dt):
        self.now += dt
        return self.now


# --------------------------------------------------------------------------
# 1. Stunt Matrix
# --------------------------------------------------------------------------

def test_stunt_matrix():
    check(
        "matrix matches Cyrus's Stunt Matrix table",
        STUNT_MATRIX == {
            "bullet_dodge": 50,
            "slide_shoot": 100,
            "air_takedown": 150,
            "wall_run_kill": 200,
            # Stage-3 additions, approved by Cyrus 2026-10-27:
            "shield_bypass": 250,
            "defenestration": 500,
        },
        f"got {STUNT_MATRIX}",
    )
    # A first-ever action is always 'new', so it scores at multiplier 1.5.
    for action, base in STUNT_MATRIX.items():
        manager = StuntManager(FakeClock())
        added, mult = manager.register(action, timestamp=0.0)
        check(
            f"matrix {action}: first action scores int({base} x 1.5)",
            added == int(base * 1.5) and mult == 1.5,
            f"got added={added} mult={mult}",
        )
        check(
            f"matrix {action}: score banked",
            manager.current_score == int(base * 1.5),
            f"got {manager.current_score}",
        )


# --------------------------------------------------------------------------
# 2. Diversity (variety) multiplier
# --------------------------------------------------------------------------

def test_diversity_rules():
    manager = StuntManager(FakeClock())
    _, mult = manager.register("bullet_dodge", timestamp=0.0)
    check("first action bumps multiplier 1.0 -> 1.5", mult == 1.5, f"got {mult}")

    # Repeating the same action never raises the multiplier.
    for i in range(4):
        _, mult = manager.register("bullet_dodge", timestamp=float(i + 1))
    check("repeating the same action does not raise multiplier",
          mult == 1.5, f"got {mult}")

    # Four distinct actions in a row climb step by step.
    climber = StuntManager(FakeClock())
    mults = []
    for i, action in enumerate(
        ["bullet_dodge", "slide_shoot", "air_takedown", "wall_run_kill"]
    ):
        _, m = climber.register(action, timestamp=float(i))
        mults.append(m)
    check("four distinct actions climb 1.5 / 2.0 / 2.5 / 3.0",
          mults == [1.5, 2.0, 2.5, 3.0], f"got {mults}")

    # Sliding last-3 window: an action still inside the window gives no bump;
    # once it falls out of the last 3, the same action counts as new again.
    slider = StuntManager(FakeClock())
    slider.register("bullet_dodge", timestamp=0.0)    # x1.5
    slider.register("slide_shoot", timestamp=3.0)     # x2.0
    slider.register("air_takedown", timestamp=6.0)    # x2.5
    _, m = slider.register("bullet_dodge", timestamp=9.0)
    check("action still inside last-3 window gives no bump", m == 2.5, f"got {m}")
    _, m = slider.register("wall_run_kill", timestamp=12.0)
    check("brand-new action bumps again (x3.0)", m == 3.0, f"got {m}")

    # Cap: rotating the four distinct moves bumps every time until x5.0.
    capper = StuntManager(FakeClock())
    cycle = ["bullet_dodge", "slide_shoot", "air_takedown", "wall_run_kill"]
    peak = 1.0
    for i in range(20):
        _, m = capper.register(cycle[i % 4], timestamp=float(i))
        peak = max(peak, m)
    check("multiplier caps at exactly 5.0", capper.combo_multiplier == 5.0,
          f"got {capper.combo_multiplier}")
    check("multiplier never exceeds 5.0", peak <= 5.0, f"peak {peak}")


# --------------------------------------------------------------------------
# 3. Explicit points, overrides, validation
# --------------------------------------------------------------------------

def test_explicit_points_and_validation():
    manager = StuntManager(FakeClock())
    added, mult = manager.register_stunt("bullet_dodge", 50, timestamp=0.0)
    check("register_stunt explicit 50 == matrix route (75 @ x1.5)",
          (added, mult) == (75, 1.5), f"got {(added, mult)}")

    added, mult = manager.register("custom_move", points=40, timestamp=0.1)
    check("points override works for an unlisted action (80 @ x2.0)",
          (added, mult) == (80, 2.0), f"got {(added, mult)}")

    check_raises("unknown action without points raises ValueError",
                 ValueError, lambda: manager.register("does_not_exist"))
    check_raises("negative points raise ValueError",
                 ValueError,
                 lambda: manager.register_stunt("bullet_dodge", -10, timestamp=0.0))
    check_raises("float points raise TypeError",
                 TypeError,
                 lambda: manager.register_stunt("bullet_dodge", 10.5, timestamp=0.0))
    check_raises("non-callable clock raises TypeError",
                 TypeError, lambda: StuntManager(None))
    check_raises("empty action name raises ValueError",
                 ValueError, lambda: manager.register_stunt("", 10, timestamp=0.0))


# --------------------------------------------------------------------------
# 4. Combo reset on player hit
# --------------------------------------------------------------------------

def test_reset_combo():
    manager = StuntManager(FakeClock())
    manager.register("bullet_dodge", timestamp=0.0)   # 75 @ x1.5
    manager.register("slide_shoot", timestamp=3.0)    # 200 @ x2.0
    check("pre-reset state: multiplier 2.0, score 275",
          manager.combo_multiplier == 2.0 and manager.current_score == 275,
          f"got mult={manager.combo_multiplier} score={manager.current_score}")
    manager.reset_combo()
    check("reset_combo returns multiplier to 1.0",
          manager.combo_multiplier == 1.0, f"got {manager.combo_multiplier}")
    check("reset_combo keeps the banked score",
          manager.current_score == 275, f"got {manager.current_score}")


# --------------------------------------------------------------------------
# 5. Multi-Kill Combo — escalation across the x2 / x3 / x5 bands
# --------------------------------------------------------------------------

def test_multi_kill_escalation():
    manager = StuntManager(FakeClock())
    returns = []
    # Five kills inside 1.7 seconds; multipliers climb via variety on top.
    returns.append(manager.register("slide_shoot", timestamp=0.0)[0])    # 150
    returns.append(manager.register("air_takedown", timestamp=0.5)[0])   # 300
    # 3rd kill: window of 3 -> band x2, bonus (150+300+500) x (2-1) = 950.
    returns.append(manager.register("wall_run_kill", timestamp=1.0)[0])  # 500+950
    # 4th kill (same move, no variety bump): window of 4 -> band x3 pays the
    # unpaid difference: 150+300+500 + 500x2 = 1950 extra.
    returns.append(manager.register("wall_run_kill", timestamp=1.5)[0])  # 500+1950
    # 5th kill: window of 5 -> band x5 pays the remaining difference: 4100.
    returns.append(manager.register("slide_shoot", timestamp=1.7)[0])    # 300+4100

    check("per-event returns incl. escalating bonuses",
          returns == [150, 300, 1450, 2450, 4400], f"got {returns}")
    check("final score after the 5-kill cluster",
          manager.current_score == 8750, f"got {manager.current_score}")
    bands = [b.band for b in manager.multi_kill_bonuses]
    points = [b.bonus_points for b in manager.multi_kill_bonuses]
    counts = [b.kills_in_window for b in manager.multi_kill_bonuses]
    check("three bonus payments recorded (one per band rise)",
          len(manager.multi_kill_bonuses) == 3,
          f"got {len(manager.multi_kill_bonuses)}")
    check("bonus bands escalate x2 -> x3 -> x5", bands == [2.0, 3.0, 5.0],
          f"got {bands}")
    check("bonus points per payment", points == [950, 1950, 4100],
          f"got {points}")
    check("kills per window grow 3 -> 4 -> 5", counts == [3, 4, 5],
          f"got {counts}")
    check("base award stored on the event excludes the bonus",
          manager.events[2].points_awarded == 500,
          f"got {manager.events[2].points_awarded}")
    check("raw base total over the cluster (100+150+200+200+100 = 750)",
          manager.raw_base_total == 750, f"got {manager.raw_base_total}")


def test_multi_kill_spread_no_bonus():
    manager = StuntManager(FakeClock())
    manager.register("slide_shoot", timestamp=0.0)   # 150 @ x1.5
    manager.register("air_takedown", timestamp=3.0)  # 300 @ x2.0
    manager.register("wall_run_kill", timestamp=6.0)  # 500 @ x2.5
    check("3 kills spread over 6s trigger NO multi-kill bonus",
          manager.multi_kill_bonuses == [],
          f"got {manager.multi_kill_bonuses}")
    check("spread-kill score is pure stunt points (950)",
          manager.current_score == 950, f"got {manager.current_score}")


def test_multi_kill_window_boundary():
    inside = StuntManager(FakeClock())
    inside.register("slide_shoot", timestamp=0.0)
    inside.register("air_takedown", timestamp=1.0)
    third = inside.register("wall_run_kill", timestamp=2.0)[0]
    check("kills at 0.0 / 1.0 / 2.0 are inside the 2.0s window -> bonus fires",
          len(inside.multi_kill_bonuses) == 1 and third == 1450,
          f"bonuses={len(inside.multi_kill_bonuses)} third={third}")

    outside = StuntManager(FakeClock())
    outside.register("slide_shoot", timestamp=0.0)
    outside.register("air_takedown", timestamp=1.0)
    third = outside.register("wall_run_kill", timestamp=2.01)[0]
    check("third kill at 2.01s falls outside -> no bonus",
          outside.multi_kill_bonuses == [] and third == 500,
          f"bonuses={len(outside.multi_kill_bonuses)} third={third}")


def test_multi_kill_band_table():
    expected = {0: 1.0, 1: 1.0, 2: 1.0, 3: 2.0, 4: 3.0, 5: 5.0, 12: 5.0}
    for kills, band in expected.items():
        check(f"band({kills} kills) == x{band}", multi_kill_band(kills) == band,
              f"got x{multi_kill_band(kills)}")


# --------------------------------------------------------------------------
# 6. TimerManager — bonus curve, pause/resume, best-time record
# --------------------------------------------------------------------------

def test_timer():
    clock = FakeClock()
    timer = TimerManager(clock, 180)
    check("elapsed is 0 before start", timer.elapsed == 0.0)
    check("S_time before start uses the full cap (180 x 100 = 18000)",
          timer.time_bonus() == 18000, f"got {timer.time_bonus()}")

    timer.start()
    clock.advance(30)
    check("elapsed 30 after advancing 30s", timer.elapsed == 30.0,
          f"got {timer.elapsed}")
    check("remaining 150", timer.remaining == 150.0, f"got {timer.remaining}")
    early_bonus = timer.time_bonus()
    check("S_time at 30s elapsed == 150 x 100 = 15000", early_bonus == 15000,
          f"got {early_bonus}")

    clock.advance(45)
    late_bonus = timer.time_bonus()
    check("S_time decreases as elapsed grows (10500 < 15000)",
          late_bonus == 10500 and late_bonus < early_bonus, f"got {late_bonus}")

    timer.pause()
    clock.advance(20)
    check("paused span is excluded from elapsed (still 75)",
          timer.elapsed == 75.0, f"got {timer.elapsed}")
    timer.resume()
    clock.advance(5)
    check("resume continues cleanly (80)", timer.elapsed == 80.0,
          f"got {timer.elapsed}")

    final = timer.finish()
    check("finish returns the final elapsed (80)", final == 80.0, f"got {final}")
    check("best_time recorded (80)", timer.best_time == 80.0,
          f"got {timer.best_time}")
    check("elapsed stays frozen after finish", timer.elapsed == 80.0)
    check("S_time at rating time uses the frozen clock (10000)",
          timer.time_bonus() == 10000, f"got {timer.time_bonus()}")

    timer.reset()
    timer.start()
    clock.advance(95)
    timer.finish()
    check("a slower run does NOT overwrite the best time",
          timer.best_time == 80.0, f"got {timer.best_time}")
    timer.reset()
    timer.start()
    clock.advance(60)
    timer.finish()
    check("a faster run DOES update the best time",
          timer.best_time == 60.0, f"got {timer.best_time}")

    check_raises("start() twice raises RuntimeError",
                 RuntimeError, lambda: (timer.reset(), timer.start(), timer.start()))
    fresh = TimerManager(FakeClock(), 60)
    check_raises("pause() before start raises RuntimeError",
                 RuntimeError, fresh.pause)
    check_raises("non-positive cap raises ValueError",
                 ValueError, lambda: TimerManager(FakeClock(), 0))

    over_clock = FakeClock()
    over = TimerManager(over_clock, 10)
    over.start()
    over_clock.advance(25)
    check("overtime remaining clamps to 0", over.remaining == 0.0,
          f"got {over.remaining}")
    check("overtime S_time is 0 (max(0, ...) — no base points)",
          over.time_bonus() == 0, f"got {over.time_bonus()}")


def test_time_bonus_formula():
    """Cyrus's sanity anchor: 85s actual vs 120s target -> S_time 3,500."""
    clock = FakeClock()
    timer = TimerManager(clock, 120)
    timer.start()
    clock.advance(85)
    check("S_time at 85/120 == (120-85) x 100 == 3500",
          timer.time_bonus() == 3500, f"got {timer.time_bonus()}")
    timer.finish()
    check("S_time stays 3500 after finish (frozen)",
          timer.time_bonus() == 3500, f"got {timer.time_bonus()}")
    check("a perfect instant finish would give 120 x 100 = 12000",
          TimerManager(FakeClock(), 120).time_bonus() == 12000)


# --------------------------------------------------------------------------
# 7. TakeRating — Cyrus's official table + approved formula
# --------------------------------------------------------------------------

def test_rating():
    boundaries = [
        (0, "F", "Re-take Required"), (2999, "F", "Re-take Required"),
        (3000, "C", "Wrap Scene"), (5999, "C", "Wrap Scene"),
        (6000, "B", "Good Take"), (9999, "B", "Good Take"),
        (10000, "A", "Box Office Hit"), (14999, "A", "Box Office Hit"),
        (15000, "S", "Perfect Take"), (40000, "S", "Perfect Take"),
    ]
    for total, want_rank, want_title in boundaries:
        got = rank_for_total(total)
        check(f"rank_for_total({total}) == ({want_rank}, '{want_title}')",
              got == (want_rank, want_title), f"got {got}")

    # Formula: S_total = S_time + int(S_stunt x M_combo), multiplier on the
    # stunt component only. Each rank is exercised under the official math:
    check("rate: 3500 + 1000x2.5 = 6000 -> B 'Good Take'",
          rate(3500, 1000, 2.5) == (6000, "B", "Good Take"),
          f"got {rate(3500, 1000, 2.5)}")
    check("rate: 3500 + 2300x5.0 = 15000 -> S 'Perfect Take'",
          rate(3500, 2300, 5.0) == (15000, "S", "Perfect Take"),
          f"got {rate(3500, 2300, 5.0)}")
    check("rate: 3500 + 500x3.0 = 5000 -> C 'Wrap Scene'",
          rate(3500, 500, 3.0) == (5000, "C", "Wrap Scene"),
          f"got {rate(3500, 500, 3.0)}")
    check("rate: 11800 + 150x2.0 = 12100 -> A 'Box Office Hit'",
          rate(11800, 150, 2.0) == (12100, "A", "Box Office Hit"),
          f"got {rate(11800, 150, 2.0)}")
    check("rate: 0 + 950x1.0 = 950 -> F 'Re-take Required'",
          rate(0, 950, 1.0) == (950, "F", "Re-take Required"),
          f"got {rate(0, 950, 1.0)}")
    check("multiplier never touches S_time (10000 + 0x5.0 stays 10000 -> A)",
          rate(10000, 0, 5.0) == (10000, "A", "Box Office Hit"),
          f"got {rate(10000, 0, 5.0)}")

    result = evaluate(3500, 1000, 2.5)
    check("evaluate breakdown: component 2500, total 6000, B 'Good Take'",
          result.s_time == 3500 and result.stunt_base == 1000
          and result.combo_multiplier == 2.5
          and result.stunt_component == 2500 and result.total == 6000
          and result.rank == "B" and result.title == "Good Take",
          f"got {result}")
    frac = evaluate(0, 275, 2.5)
    check("stunt component truncates like the house int() style (687)",
          frac.stunt_component == 687 and frac.total == 687,
          f"got {frac}")
    check_raises("negative s_time raises ValueError",
                 ValueError, lambda: rate(-1, 0, 1.0))
    check_raises("float s_stunt raises TypeError",
                 TypeError, lambda: rate(0, 1.5, 1.0))
    check_raises("zero multiplier raises ValueError",
                 ValueError, lambda: rate(0, 0, 0.0))


# --------------------------------------------------------------------------
# 8. Stunt + timer simultaneously — no interference
# --------------------------------------------------------------------------

def test_simultaneous_no_interference():
    clock = FakeClock()
    stunts = StuntManager(clock)
    timer = TimerManager(clock, 120)
    timer.start()
    clock.advance(1.0)
    added, _ = stunts.register("bullet_dodge", timestamp=clock())
    check("interleaved: dodge scores 75 @ x1.5", added == 75, f"got {added}")
    clock.advance(1.0)
    added, _ = stunts.register("slide_shoot", timestamp=clock())
    check("interleaved: slide_shoot scores 200 @ x2.0", added == 200,
          f"got {added}")
    check("timer tracks the shared clock (2.0s)", timer.elapsed == 2.0,
          f"got {timer.elapsed}")
    check("S_time at 2s elapsed == 118 x 100 = 11800",
          timer.time_bonus() == 11800, f"got {timer.time_bonus()}")
    clock.advance(3.0)
    check("stunt events do not move the timer (5.0s)",
          timer.elapsed == 5.0, f"got {timer.elapsed}")
    check("timer does not touch the live stunt score (275)",
          stunts.current_score == 275, f"got {stunts.current_score}")
    check("raw stunt base sum for the rating formula (50 + 100 = 150)",
          stunts.raw_base_total == 150, f"got {stunts.raw_base_total}")
    # Final take under Cyrus's formula at 5s elapsed:
    # S_time = 115 x 100 = 11500; S_stunt = 150 raw; M_combo = 2.0.
    graded = rate(timer.time_bonus(), stunts.raw_base_total,
                  stunts.combo_multiplier)
    check("combined take: 11500 + 150x2.0 = 11800 -> A 'Box Office Hit'",
          graded == (11800, "A", "Box Office Hit"), f"got {graded}")


# --------------------------------------------------------------------------
# 13. Stage-3 stunt actions (Cyrus 2026-10-27): defenestration + shield_bypass
# --------------------------------------------------------------------------

def test_stage3_stunt_actions():
    check("matrix: defenestration == 500 PTS",
          STUNT_MATRIX.get("defenestration") == 500,
          f"got {STUNT_MATRIX.get('defenestration')}")
    check("matrix: shield_bypass == 250 PTS",
          STUNT_MATRIX.get("shield_bypass") == 250,
          f"got {STUNT_MATRIX.get('shield_bypass')}")
    # Through register(): a fresh manager's first action is new, so the
    # multiplier rises to x1.5 BEFORE scoring (the manager's core rule):
    # defenestration must bank int(500 x 1.5) = 750 with base 500 recorded.
    clock = FakeClock()
    sm = StuntManager(clock)
    added, mult = sm.register("defenestration")
    event = sm.events[-1]
    check("register('defenestration') scores 500 base through the combo math",
          event.base_points == 500 and added == 750 and mult == 1.5,
          f"base={event.base_points} added={added} mult={mult}")
    clock2 = FakeClock()
    sm2 = StuntManager(clock2)
    added2, mult2 = sm2.register("shield_bypass")
    event2 = sm2.events[-1]
    check("register('shield_bypass') scores 250 base through the combo math",
          event2.base_points == 250 and added2 == 375 and mult2 == 1.5,
          f"base={event2.base_points} added={added2} mult={mult2}")


SECTIONS = [
    ("Stunt Matrix", test_stunt_matrix),
    ("Stage-3 stunt actions", test_stage3_stunt_actions),
    ("Diversity multiplier", test_diversity_rules),
    ("Explicit points & validation", test_explicit_points_and_validation),
    ("Combo reset", test_reset_combo),
    ("Multi-Kill escalation", test_multi_kill_escalation),
    ("Multi-Kill spread (no bonus)", test_multi_kill_spread_no_bonus),
    ("Multi-Kill window boundary", test_multi_kill_window_boundary),
    ("Multi-Kill band table", test_multi_kill_band_table),
    ("TimerManager", test_timer),
    ("S_time formula sanity (85/120)", test_time_bonus_formula),
    ("TakeRating", test_rating),
    ("Simultaneous stunt+timer", test_simultaneous_no_interference),
]


def main() -> int:
    print("=" * 72)
    print("Action Star: NYC Siege 3D — logic core QA (deterministic)")
    print("=" * 72)
    crashed = []
    for title, fn in SECTIONS:
        print(f"\n--- {title} ---")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a crash is a failed section
            crashed.append((title, exc))
            print(f"[FAIL] section '{title}' crashed: {type(exc).__name__}: {exc}")
    failed = [name for name, ok in RESULTS if not ok]
    print("\n" + "=" * 72)
    print(
        f"SUMMARY: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed, "
        f"{len(failed)} failed, {len(crashed)} sections crashed"
    )
    if failed:
        print("FAILED CHECKS:")
        for name in failed:
            print(f"  - {name}")
    if crashed:
        print("CRASHED SECTIONS:")
        for title, exc in crashed:
            print(f"  - {title}: {type(exc).__name__}: {exc}")
    verdict = "ALL CHECKS PASSED" if not failed and not crashed else "FAILURES PRESENT"
    print(f"VERDICT: {verdict}")
    return 0 if not failed and not crashed else 1


if __name__ == "__main__":
    sys.exit(main())
