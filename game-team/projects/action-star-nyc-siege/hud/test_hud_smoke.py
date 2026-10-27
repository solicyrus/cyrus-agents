"""Headless QA smoke test for hud.hud_manager.HUDManager (Ursina).

Proves the HUD does not interfere with the host loop and displays exactly
the state it is given:

  * builds a minimal scene + HUDManager under a real GL context (Xvfb);
  * drives a scripted ~5 s run: the elapsed timer advances, three stunt
    notifications fire (incl. +200 WALL-RUN KILL), the combo rises to 3.5x
    (which must spawn the combo announcement), HP drops 100 -> 62, and the
    Bullet Time charge drains 100 -> 35 and refills to 100 (READY state);
  * asserts: no exception across all frames, feed entries were created and
    expired on schedule, and the on-screen texts track the scripted state
    (read back from the live Text entities, including the final
    "STUNT SCORE: 12,450" comma formatting and "(Target: 02:00.00)").

The S_total math itself is covered by the logic package's own tests; this
test only asserts the HUD displays the totals it is handed.

Run:  xvfb-run -a /tmp/ursina-venv/bin/python hud/test_hud_smoke.py
Exit code 0 = PASS, 1 = FAIL. PROOF lines go to stdout.
"""

import os
import sys
import time as _time

# Make the project root importable no matter where the script is run from.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from ursina import Entity, Ursina, application, color  # noqa: E402

from hud.hud_manager import HUDManager, format_time  # noqa: E402

RUN_SECONDS = 5.2
TARGET_S = 120.0

app = Ursina(title="Action Star — HUD smoke", vsync=False)

# Minimal scene so a real frame is rendered behind the HUD.
Entity(model="cube", scale=(30, 0.5, 30), position=(0, -0.25, 0),
       color=color.rgb(70, 74, 84))
Entity(model="cube", scale=(1, 1.8, 1), position=(0, 0.9, -6),
       color=color.orange)

hud = HUDManager(target_s=TARGET_S)

results = {"failures": [], "checks": 0}


def check(name, ok, detail=""):
    results["checks"] += 1
    line = f"PROOF check {name}: {'OK' if ok else 'FAIL'} {detail}".rstrip()
    print(line, flush=True)
    if not ok:
        results["failures"].append(name)


def expect(name, ok, detail=""):
    check(name, bool(ok), detail)


# --------------------------------------------------------------------------
# Scripted driver — runs inside the engine update loop
# --------------------------------------------------------------------------
started = _time.perf_counter()
flags = {"stunts_fired": False, "combo_set": False, "mid_readback": False,
         "finished": False}
frames = 0


def scripted_state(elapsed):
    """Piecewise scripted game state for time `elapsed` (seconds)."""
    hp = 100.0 if elapsed < 1.5 else 62.0
    if elapsed < 1.0:
        charge = 100.0
    elif elapsed < 2.5:
        charge = 100.0 - (elapsed - 1.0) / 1.5 * 65.0      # drain to 35
    elif elapsed < 4.5:
        charge = 35.0 + (elapsed - 2.5) / 2.0 * 65.0       # refill to 100
    else:
        charge = 100.0
    score = 0 if elapsed < 0.85 else 400 if elapsed < 2.0 else 12450
    combo = 1.0 if elapsed < 0.8 else 3.5
    actions = [] if elapsed < 0.8 else ["WALL-RUN KILL", "AIR TAKEDOWN"]
    return hp, charge, score, combo, actions


def update():
    global frames
    frames += 1
    elapsed = _time.perf_counter() - started
    hp, charge, score, combo, actions = scripted_state(elapsed)

    if elapsed >= 0.3 and not flags["stunts_fired"]:
        flags["stunts_fired"] = True
        hud.notify(200, "WALL-RUN KILL")
        hud.notify(150, "AIR TAKEDOWN")
        hud.notify(50, "BULLET DODGE")

    try:
        hud.update_state(hp=hp, bullet_charge=charge, elapsed_s=elapsed,
                         target_s=TARGET_S, stunt_score=score, combo=combo,
                         last_actions=actions)
    except Exception as exc:  # the HUD must never break the host loop
        check("no_exception_in_update_state", False, repr(exc))
        flags["finished"] = True
        application.quit()
        return

    if elapsed >= 0.8 and not flags["combo_set"]:
        flags["combo_set"] = True
        hud.set_combo(3.5)   # explicit API path — must announce the increase

    if elapsed >= 1.0 and not flags["mid_readback"]:
        flags["mid_readback"] = True
        feed = hud.feed_texts()
        expect("feed_shows_wall_run_kill",
               any("WALL-RUN KILL" in t and "+200 PTS" in t for t in feed),
               f"feed={feed}")
        expect("feed_shows_combo_announcement",
               any("COMBO MULTIPLIER INCREASED TO 3.5x" in t for t in feed),
               f"feed={feed}")
        expect("feed_entries_active_mid_run", hud.active_feed_count() >= 4,
               f"active={hud.active_feed_count()}")

    if elapsed >= RUN_SECONDS and not flags["finished"]:
        flags["finished"] = True
        finish(elapsed)


def finish(elapsed):
    expect("no_exception_in_update_state", True,
           f"frames={frames} all update_state calls returned")
    expect("frames_sane", frames >= 50, f"frames={frames} in {elapsed:.2f}s")
    expect("notifications_spawned", hud.total_notifications >= 4,
           f"spawned={hud.total_notifications} (3 stunts + >=1 combo)")
    expect("feed_entries_expired", hud.total_expired >= 3,
           f"expired={hud.total_expired} (lifetime is 2.6s, run "
           f"{RUN_SECONDS}s)")
    expect("feed_pool_drained", hud.active_feed_count() == 0,
           f"active={hud.active_feed_count()}")

    time_str = hud.time_text.text
    expect("time_text_tracks_state",
           format_time(elapsed)[:4] in time_str
           and "(Target: 02:00.00)" in time_str,
           f"time_text={time_str!r}")
    expect("score_text_tracks_state",
           "STUNT SCORE: 12,450" in hud.score_text.text,
           f"score_text={hud.score_text.text!r}")
    expect("combo_text_tracks_state",
           "3.5x" in hud.combo_text.text
           and "WALL-RUN" in hud.combo_text.text,
           f"combo_text={hud.combo_text.text!r}")
    expect("hp_text_tracks_state", "62%" in hud.hp_label.text,
           f"hp_label={hud.hp_label.text!r}")
    expect("bullet_time_ready_state",
           "READY" in hud.bullet_status.text
           and "100%" in hud.bullet_label.text,
           f"status={hud.bullet_status.text!r} "
           f"label={hud.bullet_label.text!r}")

    verdict = "PASS" if not results["failures"] else "FAIL"
    print(f"PROOF hud_smoke {verdict}: {results['checks']} checks, "
          f"{len(results['failures'])} failures, frames={frames}, "
          f"spawned={hud.total_notifications}, "
          f"expired={hud.total_expired}", flush=True)
    application.quit()


app.run()

sys.exit(0 if not results["failures"] else 1)
