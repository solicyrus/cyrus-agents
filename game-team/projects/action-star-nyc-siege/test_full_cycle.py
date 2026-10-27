"""Full-cycle QA test for Action Star: NYC Siege 3D — the FINAL
wiring acceptance test (Cyrus's order, 2026-10-27).

ONE process boots the REAL packaged entry (phase4.game_entry) against
a throwaway HOME (all saves land in a temp dir) and drives the whole
cycle through the shell's own code paths:

    main menu -> (STAGE SELECT probe: cards shown, locked card inert)
    -> START GAME -> FullGamePipeline: Lobby -> elevator transition
    -> Data Center -> elevator transition -> Penthouse + boss fight
    -> Final Take card on the real VictoryScreen -> BACK TO MENU
    -> HIGH SCORES (menu still responsive) -> back to menu.

The floors are played by the same scripted autopilot as
test_full_pipeline.py, injected through game_entry.set_input_provider
— the exact seam a human player's keyboard uses in pump().

Asserted, against the run's own numbers:
  * the applied time-bank bonus cap (Cyrus's +30 s order): unit-level
    (84.3 s banked applies +30.0 exactly; 12 s applies +12) AND live
    (floor 2's cap == 75 + min(lobby banked, 30), floor 3's ==
    105 + min(Data Center banked, 30));
  * both elevator transitions render (>30 frames) carrying the
    finished floors' real stats;
  * the boss is defeated and all three floors settle as WINs;
  * the final card on the VictoryScreen shows the pipeline's own
    rank / S_total, with S_total == SUM(floor S_time) + raw stunt
    base x final combo recomputed independently;
  * BACK TO MENU returns control to a live MainMenuState (pipeline
    disposed, menu active, HIGH SCORES opens and shows this run's
    records);
  * the temp user_progress.json on disk holds records for all three
    floors FROM THIS RUN (best score/time/rank == the floors' own
    numbers) and all levels unlocked.

FPS per segment is logged (sandbox software rendering under Xvfb —
not a GPU prediction). Exit code 0 = PASS, 1 = FAIL; PROOF lines go
to stdout. Cyrus's verification rule: this test must pass on TWO
consecutive executions — see FINAL-CYCLE-REPORT.md.

Run:  xvfb-run -a /tmp/ursina-venv/bin/python test_full_cycle.py
"""

import json
import logging
import math
import os
import sys
import tempfile
import time as _time

# Throwaway HOME before ANY module resolves a user path: the shared
# SaveManager (and phase4 settings) land inside it, so this run's
# saves are provably this run's.
_TMP_HOME = tempfile.mkdtemp(prefix="actionstar-cycle-")
os.environ["HOME"] = _TMP_HOME
SAVE_PATH = os.path.join(_TMP_HOME, ".actionstar", "user_progress.json")

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from ursina import Vec3  # noqa: E402
from ursina import time as ursina_time  # noqa: E402

from logic import take_rating  # noqa: E402
from logic.timer_manager import TimerManager  # noqa: E402
from pipeline_state import BANK_BONUS_CAP_S, RunState  # noqa: E402
from level1.player_controller_3d import PlayerInput  # noqa: E402

results = {"failures": [], "checks": 0}


def check(name, ok, detail=""):
    results["checks"] += 1
    line = f"PROOF check {name}: {'OK' if ok else 'FAIL'} {detail}".rstrip()
    print(line, flush=True)
    if not ok:
        results["failures"].append(name)


def expect(name, ok, detail=""):
    check(name, bool(ok), detail)


# ===========================================================================
# Part 0 — the +30 s applied time-bank cap, unit level (Cyrus's order)
# ===========================================================================
class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


expect("cap_constant_is_30", BANK_BONUS_CAP_S == 30.0,
       f"BANK_BONUS_CAP_S={BANK_BONUS_CAP_S}")

rs_cap = RunState()
rs_cap.banked_seconds = 84.3
expect("unit_bank_84_3_applies_plus_30_exactly",
       rs_cap.effective_target(75.0) == 105.0
       and rs_cap.effective_target(105.0) == 135.0,
       f"banked 84.3 -> floor targets {rs_cap.effective_target(75.0)} / "
       f"{rs_cap.effective_target(105.0)} (base + 30.0, not +84.3)")
rs_cap.banked_seconds = 12.0
expect("unit_bank_12_applies_plus_12",
       rs_cap.effective_target(75.0) == 87.0,
       f"banked 12.0 -> floor target {rs_cap.effective_target(75.0)}")

# Through a real settle: a floor ending with 84.3 s remaining accrues
# the full 84.3 in the run state, but the next floor applies +30.0.
rs_settle = RunState()
_clock = FakeClock()
_timer = TimerManager(_clock, rs_settle.effective_target(90.0))
rs_settle.attach_timer(_timer)
_timer.start()
_clock.now = 5.7               # 84.3 s remaining on the 90 s floor
_timer.finish()
_rec = rs_settle.settle_floor(level_num=1, timer=_timer, won=True,
                              reason="unit cap", hp_end_pre_heal=100.0,
                              stunt_base_start=0)
expect("unit_settle_84_3_accrues_full_applies_30",
       abs(_rec.banked_out_s - 84.3) < 0.01
       and abs(rs_settle.banked_seconds - 84.3) < 0.01
       and rs_settle.effective_target(75.0) == 105.0,
       f"banked_out={_rec.banked_out_s} accrued="
       f"{rs_settle.banked_seconds:.2f} next floor cap="
       f"{rs_settle.effective_target(75.0)}")

# ===========================================================================
# Part 1 — boot the REAL entry point
# ===========================================================================
from phase4 import game_entry as entry  # noqa: E402

app = entry.app
menu = entry.menu
victory_screen = entry.victory_screen

started = _time.perf_counter()
GLOBAL_TIMEOUT_S = 560.0
frames = 0
done = {"finished": False}
stage = {"name": "boot", "t0": started, "f0": 0}

# Per-segment accounting: name -> [t0, f0, t1, f1]
segments = {}
seg_order = []


def open_segment(name):
    if name in segments:
        return
    segments[name] = [_time.perf_counter(), frames, None, None]
    seg_order.append(name)


def close_segment(name):
    seg = segments.get(name)
    if seg is not None and seg[2] is None:
        seg[2] = _time.perf_counter()
        seg[3] = frames


def set_stage(name):
    stage["name"] = name
    stage["t0"] = _time.perf_counter()
    stage["f0"] = frames
    print(f"PROOF cycle stage -> {name}", flush=True)


def stage_elapsed():
    return _time.perf_counter() - stage["t0"]


def stage_frames():
    return frames - stage["f0"]


# ===========================================================================
# Autopilot — the proven routes of test_full_pipeline.py, driven
# through game_entry's input-provider seam. `pipeline` is refreshed
# from the entry every frame.
# ===========================================================================
pipeline = None
A = {}   # autopilot scratch, reset per sub-phase
sub = {"name": None}


def set_sub(name):
    if sub["name"] != name:
        sub["name"] = name
        A.clear()
        print(f"PROOF autopilot -> {name}", flush=True)


def yaw_pitch_to(src, dst):
    d = dst - src
    yaw = math.degrees(math.atan2(d.x, d.z))
    pitch = math.degrees(math.atan2(d.y, math.hypot(d.x, d.z)))
    return yaw, pitch


def nav(points, timeout_s):
    """Waypoint following + stuck detector (test_full_pipeline's)."""
    if "wps" not in A:
        A["wps"] = list(points)
        A["t0"] = _time.perf_counter()
        A["stuck_ref"] = None
        A["stuck_since"] = _time.perf_counter()
        A["detours"] = 0
    player = pipeline.session.player
    now = _time.perf_counter()
    if A["stuck_ref"] is None:
        A["stuck_ref"] = Vec3(player.position.x, 0, player.position.z)
    while A["wps"]:
        target = A["wps"][0]
        rel = Vec3(target.x - player.position.x, 0,
                   target.z - player.position.z)
        if rel.length() < 0.6:
            A["wps"].pop(0)
            A["stuck_ref"] = Vec3(player.position.x, 0, player.position.z)
            A["stuck_since"] = now
            continue
        moved = (Vec3(player.position.x, 0, player.position.z)
                 - A["stuck_ref"]).length()
        if moved > 1.2:
            A["stuck_ref"] = Vec3(player.position.x, 0, player.position.z)
            A["stuck_since"] = now
        elif now - A["stuck_since"] > 1.5 and A["detours"] < 4:
            direction = rel.normalized()
            sign = 1.0 if A["detours"] % 2 == 0 else -1.0
            perp = Vec3(-direction.z * sign, 0, direction.x * sign) * 2.6
            detour = Vec3(player.position.x + perp.x, 0,
                          player.position.z + perp.z)
            A["wps"].insert(0, detour)
            A["detours"] += 1
            A["stuck_ref"] = Vec3(player.position.x, 0, player.position.z)
            A["stuck_since"] = now
            print(f"PROOF autopilot: stuck at ({player.position.x:.1f},"
                  f"{player.position.z:.1f}) — detour via "
                  f"({detour.x:.1f},{detour.z:.1f})", flush=True)
            continue
        yaw, pitch = yaw_pitch_to(player.position, target)
        return PlayerInput(move=rel.normalized(), aim_yaw=yaw,
                           aim_pitch=pitch), False
    return PlayerInput(), True


def goto(target, aim_point=None):
    player = pipeline.session.player
    rel = Vec3(target.x - player.position.x, 0,
               target.z - player.position.z)
    dist = rel.length()
    yaw, pitch = yaw_pitch_to(player.position + Vec3(0, 0.5, 0),
                              aim_point or target)
    move = rel.normalized() if dist > 0.05 else Vec3(0, 0, 0)
    return PlayerInput(move=move, aim_yaw=yaw, aim_pitch=pitch), dist


def sub_elapsed():
    return _time.perf_counter() - A.get("t0", started)


def auto_floor1():
    session = pipeline.session
    player = session.player
    g2 = session.guards[1]
    if sub["name"] is None:
        set_sub("f1_melee_g2")
    if sub["name"] == "f1_melee_g2":
        if "t0" not in A:
            A["t0"] = _time.perf_counter()
        rel = g2.position - player.position
        rel.y = 0
        dist = rel.length()
        yaw, _ = yaw_pitch_to(player.position, g2.position)
        move = rel.normalized() if dist > 1.6 else Vec3(0, 0, 0)
        inp = PlayerInput(move=move, aim_yaw=yaw, aim_pitch=0.0,
                          melee=dist < 2.2)
        if not g2.alive:
            print("PROOF autopilot: G2 down (melee)", flush=True)
            set_sub("f1_to_elevator")
        elif sub_elapsed() > 25.0:
            print("PROOF autopilot: G2 fight timed out — pushing on "
                  "to the elevator (legal: clear OR slip past)", flush=True)
            set_sub("f1_to_elevator")
        return inp
    inp, arrived = nav([Vec3(8, 0, 6), Vec3(3, 0, 10.5), Vec3(0, 0, 13.2)],
                       20.0)
    return inp


def auto_floor2():
    session = pipeline.session
    player = session.player
    mrk = session.marksman
    if sub["name"] is None:
        set_sub("f2_to_marksman")
    if sub["name"] == "f2_to_marksman":
        if "t0" not in A:
            A["t0"] = _time.perf_counter()
        if "at_post" not in A:
            inp, arrived = nav([Vec3(9, 0, -10.5), Vec3(13.5, 0, -4),
                                Vec3(17.2, 0, -1)], 20.0)
            if not arrived:
                if not player.bt_active and player.charge > 30.0:
                    inp.bullet_time = True
                return inp
            A["at_post"] = True
        rel = mrk.position - player.position
        rel.y = 0
        dist = rel.length()
        yaw, _ = yaw_pitch_to(player.position, mrk.position)
        move = rel.normalized() if dist > 1.9 else Vec3(0, 0, 0)
        inp = PlayerInput(move=move, aim_yaw=yaw, aim_pitch=0.0,
                          melee=dist < 2.2)
        if not player.bt_active and player.charge > 30.0:
            inp.bullet_time = True
        if not mrk.alive:
            print("PROOF autopilot: Data Center marksman down (melee)",
                  flush=True)
            set_sub("f2_to_goal")
        elif sub_elapsed() > 35.0:
            print("PROOF autopilot: marksman fight timed out — heading "
                  "to the elevator", flush=True)
            set_sub("f2_to_goal")
        return inp
    inp, _dist = goto(Vec3(18, 0, 11.2))
    return inp


def auto_floor3():
    session = pipeline.session
    player = session.player
    mrk = session.marksman
    boss = session.boss
    if sub["name"] is None:
        set_sub("f3_marksman_bt")
    if sub["name"] == "f3_marksman_bt":
        if "t0" not in A:
            A["t0"] = _time.perf_counter()
        inp = None
        if "at_post" not in A:
            inp, arrived = nav([Vec3(10, 0, -13.3), Vec3(16.3, 0, -12.3)],
                               20.0)
            if arrived:
                A["at_post"] = True
                inp = None
        if inp is None:
            rel = mrk.position - player.position
            rel.y = 0
            dist = rel.length()
            yaw, _ = yaw_pitch_to(player.position, mrk.position)
            move = rel.normalized() if dist > 1.9 else Vec3(0, 0, 0)
            inp = PlayerInput(move=move, aim_yaw=yaw, aim_pitch=0.0,
                              melee=dist < 2.2)
        if not player.bt_active and player.charge > 30.0:
            inp.bullet_time = True
        if not mrk.alive:
            print("PROOF autopilot: Penthouse marksman down (melee)",
                  flush=True)
            if player.bt_active:
                inp2 = PlayerInput(bullet_time=True)
                set_sub("f3_boss")
                return inp2
            set_sub("f3_boss")
        elif sub_elapsed() > 35.0:
            print("PROOF autopilot: penthouse marksman timed out — "
                  "engaging the boss anyway", flush=True)
            set_sub("f3_boss")
        return inp
    if "t0" not in A:
        A["t0"] = _time.perf_counter()
    to_center = Vec3(-boss.position.x, 0, -boss.position.z)
    if to_center.length() < 0.1:
        to_center = Vec3(0, 0, -1)
    standoff_dist = 12.0 if player.hp < 30.0 else 8.0
    standoff = boss.position + to_center.normalized() * standoff_dist
    rel = Vec3(standoff.x - player.position.x, 0,
               standoff.z - player.position.z)
    move = rel.normalized() if rel.length() > 0.9 else Vec3(0, 0, 0)
    yaw, pitch = yaw_pitch_to(player.position + Vec3(0, 0.5, 0),
                              boss.position + Vec3(0, 0.35, 0))
    inp = PlayerInput(move=move, aim_yaw=yaw, aim_pitch=pitch, shoot=True)
    if not player.bt_active and player.charge >= 95.0:
        inp.bullet_time = True
    elif player.bt_active and player.charge <= 10.0:
        inp.bullet_time = True
    return inp


AUTOPILOTS = {1: auto_floor1, 2: auto_floor2, 3: auto_floor3}


def autopilot_provider():
    global pipeline
    pipeline = entry.active_pipeline()
    if pipeline is None or pipeline.phase != "floor" \
            or pipeline.session is None:
        return PlayerInput()
    return AUTOPILOTS[pipeline.session.level_num]()


entry.set_input_provider(autopilot_provider)


# ===========================================================================
# Observation — segments, transitions, floor starts
# ===========================================================================
obs = {"floor": None, "trans_from": None}
transitions_seen = {}
floor_starts = {}        # level_num -> {"cap": float}
final_card = {}          # captured VictoryScreen texts + pipeline record


def observe():
    pipe = entry.active_pipeline()
    # Segment bookkeeping.
    if pipe is None:
        seg = "menu"
    elif pipe.phase == "floor" and pipe.session is not None:
        seg = f"floor{pipe.session.level_num}"
    elif pipe.phase == "transition":
        seg = f"transition{(pipe.transition.record.level_num
                            if pipe.transition.record else '?')}"
    elif pipe.phase in ("final", "failed"):
        seg = "victory_card"
    else:
        seg = pipe.phase
    open_segment(seg)
    for name in list(segments):
        if name != seg:
            close_segment(name)

    if pipe is None:
        obs["floor"] = None
        return
    if pipe.phase == "floor" and pipe.session is not None:
        num = pipe.session.level_num
        if obs["trans_from"] is not None:
            transitions_seen[obs["trans_from"]]["frames"] = \
                pipe.transition.frames
            obs["trans_from"] = None
        if obs["floor"] != num:
            obs["floor"] = num
            sub["name"] = None
            A.clear()
            floor_starts[num] = {"cap": pipe.session.timer.time_cap}
            recs = {r.level_num: r for r in pipe.run_state.floor_records}
            print(f"PROOF floor {num} started via entry: cap="
                  f"{pipe.session.timer.time_cap:.2f}s "
                  f"records_so_far={sorted(recs)}", flush=True)
            if num == 2 and 1 in recs:
                r1 = recs[1]
                want = 75.0 + min(r1.banked_out_s, BANK_BONUS_CAP_S)
                expect("floor2_cap_is_75_plus_min_bank_30",
                       abs(pipe.session.timer.time_cap - want) < 0.01
                       and abs(r1.banked_in_s - 0.0) < 0.01,
                       f"cap={pipe.session.timer.time_cap:.2f} want "
                       f"{want:.2f} = 75 + min({r1.banked_out_s:.2f}, 30)")
            if num == 3 and 2 in recs:
                r2 = recs[2]
                want = 105.0 + min(r2.banked_out_s, BANK_BONUS_CAP_S)
                expect("floor3_cap_is_105_plus_min_bank_30",
                       abs(pipe.session.timer.time_cap - want) < 0.01,
                       f"cap={pipe.session.timer.time_cap:.2f} want "
                       f"{want:.2f} = 105 + min({r2.banked_out_s:.2f}, 30)")
    elif pipe.phase == "transition":
        rec = pipe.transition.record
        if rec is not None and obs["trans_from"] != rec.level_num:
            obs["trans_from"] = rec.level_num
            transitions_seen[rec.level_num] = {
                "title": pipe.transition.title_text_value,
                "stats": pipe.transition.stats_text_value,
                "frames": None,
            }
            print(f"PROOF transition after floor {rec.level_num} shown:\n"
                  f"{pipe.transition.title_text_value}\n"
                  f"{pipe.transition.stats_text_value}", flush=True)
    else:
        if obs["trans_from"] is not None:
            num = obs["trans_from"]
            transitions_seen[num]["frames"] = pipe.transition.frames
            obs["trans_from"] = None


# ===========================================================================
# End-of-cycle assertions
# ===========================================================================
def run_end_assertions():
    pipe = entry.active_pipeline()
    expect("pipeline_disposed_after_menu_return", pipe is None,
           f"active_pipeline={pipe}")
    # The run object is gone from the entry; its records were captured
    # at the victory stage.
    records = final_card.get("records", [])
    by_num = {r.level_num: r for r in records}
    expect("three_floors_settled_in_cycle", len(records) == 3,
           f"records={[(r.level_num, r.outcome, r.floor_rank) for r in records]}")
    if len(records) == 3:
        r1, r2, r3 = by_num[1], by_num[2], by_num[3]
        expect("all_floors_won", all(r.outcome == "WIN" for r in records),
               f"outcomes={[(r.level_num, r.outcome, r.reason) for r in records]}")
        expect("boss_defeated_in_cycle", r3.boss_defeated is True,
               f"boss_defeated={r3.boss_defeated}")
        expect("stunt_continuity_in_cycle",
               r2.stunt_base_start == r1.stunt_base_end
               and r3.stunt_base_start == r2.stunt_base_end
               and r1.stunt_base_end > 0,
               f"raw chain {r1.stunt_base_start}->{r1.stunt_base_end}"
               f"->{r2.stunt_base_end}->{r3.stunt_base_end}")
        for num, rec in ((1, r1), (2, r2)):
            seen = transitions_seen.get(num)
            ok = (seen is not None and (seen["frames"] or 0) > 30
                  and rec.stage_name.upper() in seen["title"]
                  and "ELEVATOR" in seen["title"]
                  and f"RANK {rec.floor_rank}" in seen["stats"]
                  and f"{rec.s_time:,}" in seen["stats"])
            expect(f"transition_after_floor{num}_rendered", ok,
                   f"seen={None if seen is None else (seen['frames'], seen['title'])}")
    # The save file from THIS run (temp HOME).
    expect("save_file_exists", os.path.exists(SAVE_PATH), SAVE_PATH)
    if os.path.exists(SAVE_PATH):
        with open(SAVE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        expect("save_all_levels_unlocked",
               data.get("unlocked_levels") == [1, 2, 3],
               f"unlocked={data.get('unlocked_levels')}")
        for rec in records:
            saved = data["levels_data"][f"level_{rec.level_num}"]
            expect(f"save_record_floor{rec.level_num}_from_this_run",
                   saved["best_score"] == rec.floor_s_total
                   and saved["best_rank"] == rec.floor_rank
                   and abs(saved["best_time"] - rec.t_actual_s) < 0.01,
                   f"saved={saved} floor_total={rec.floor_s_total} "
                   f"rank={rec.floor_rank} t={rec.t_actual_s}")


def print_segments_and_card():
    print("\n================ SEGMENTS (FPS) ================", flush=True)
    for name in seg_order:
        t0, f0, t1, f1 = segments[name]
        if t1 is None:
            t1, f1 = _time.perf_counter(), frames
        wall = t1 - t0
        fps = (f1 - f0) / wall if wall > 0 else 0.0
        print(f"SEGMENT {name}: {f1 - f0} frames in {wall:.2f}s "
              f"= {fps:.1f} fps", flush=True)
    print("================================================", flush=True)
    if final_card:
        print("\n================ FINAL TAKE CARD (verbatim, "
              "VictoryScreen) ================", flush=True)
        print(final_card.get("heading", ""), flush=True)
        print(f"RANK {final_card.get('rank', '')} — "
              f"{final_card.get('title', '')}", flush=True)
        print(final_card.get("breakdown", ""), flush=True)
        print(final_card.get("detail", ""), flush=True)
        print("==================================================="
              "=============", flush=True)


def finish_all():
    if done["finished"]:
        return
    done["finished"] = True
    for name in list(segments):
        close_segment(name)
    run_end_assertions()
    print_segments_and_card()
    elapsed = _time.perf_counter() - started
    fps = frames / elapsed if elapsed > 0 else 0.0
    print(f"PROOF cycle frames={frames} elapsed={elapsed:.2f}s "
          f"avg_fps={fps:.1f} (sandbox software rendering) "
          f"tmp_home={_TMP_HOME}", flush=True)
    verdict = "PASS" if not results["failures"] else "FAIL"
    print(f"PROOF full_cycle {verdict}: {results['checks']} checks, "
          f"{len(results['failures'])} failures: {results['failures']}",
          flush=True)
    sys.stdout.flush()
    os._exit(0 if not results["failures"] else 1)


# ===========================================================================
# The cycle stage machine
# ===========================================================================
def cycle_step():
    pipe = entry.active_pipeline()
    name = stage["name"]

    if name == "boot":
        open_segment("menu")
        if stage_frames() >= 45:
            expect("boot_main_menu_up",
                   menu.active and bool(menu.ui_root.enabled)
                   and menu.last_action is None
                   and entry.active_pipeline() is None,
                   f"menu.active={menu.active} last_action={menu.last_action}")
            expect("wiring_stage_floor_map",
                   entry.STAGE_ID_BY_FLOOR == {1: "lobby",
                                               2: "data_center",
                                               3: "penthouse"}
                   and entry.level_select.on_level_chosen is not None
                   and menu.level_select is entry.level_select_host,
                   f"map={entry.STAGE_ID_BY_FLOOR}")
            menu.press_stage_select()
            set_stage("probe_select")
        return

    if name == "probe_select":
        if stage_frames() >= 15:
            shown = all(e.enabled for e in entry.level_select._entities)
            card3 = entry.level_select.activate_card(3)
            expect("level_select_shows_and_locked_card_inert",
                   shown and card3 is None
                   and entry.active_pipeline() is None
                   and "LOCKED" in entry.level_select.card_text(3)
                   and "Lobby" in entry.level_select.card_text(1),
                   f"shown={shown} activate_card(3)={card3}")
            entry.level_select.back_button.on_click()
            set_stage("probe_back")
        return

    if name == "probe_back":
        if stage_frames() >= 15:
            hidden = not any(e.enabled
                             for e in entry.level_select._entities)
            expect("level_select_back_returns_to_menu",
                   hidden and menu.active and bool(menu.ui_root.enabled),
                   f"hidden={hidden} menu.active={menu.active}")
            menu.press_start()
            pipe = entry.active_pipeline()
            expect("start_game_begins_pipeline_floor1",
                   pipe is not None and pipe.phase == "floor"
                   and pipe.session is not None
                   and pipe.session.level_num == 1
                   and not menu.active
                   and menu.last_action == "start"
                   and menu.last_stage == "lobby",
                   f"pipeline={pipe is not None} "
                   f"floor={None if pipe is None or pipe.session is None else pipe.session.level_num} "
                   f"last_action={menu.last_action}")
            set_stage("run")
        return

    if name == "run":
        if pipe is not None and pipe.phase in ("final", "failed"):
            fr = pipe.final_record
            final_card["records"] = list(pipe.run_state.floor_records)
            final_card["record"] = fr
            final_card["heading"] = victory_screen.heading.text
            final_card["rank"] = victory_screen.rank_text.text
            final_card["title"] = victory_screen.title_text.text
            final_card["breakdown"] = victory_screen.breakdown.text
            final_card["detail"] = victory_screen.detail.text
            # Independent recomputation of the card's arithmetic.
            run = pipe.run_state
            recomputed = take_rating.evaluate(
                sum(r.s_time for r in run.floor_records),
                run.stunt.raw_base_total, run.stunt.combo_multiplier)
            expect("final_card_on_victory_screen",
                   victory_screen.visible
                   and victory_screen.outcome == "victory"
                   and fr is not None
                   and victory_screen.rank_text.text == fr["rank"]
                   and fr["s_total"] == recomputed.total
                   and f"{fr['s_total']:,}" in victory_screen.breakdown.text,
                   f"visible={victory_screen.visible} outcome="
                   f"{victory_screen.outcome} screen_rank="
                   f"{victory_screen.rank_text.text} pipeline="
                   f"{None if fr is None else (fr['rank'], fr['s_total'])} "
                   f"recomputed={recomputed.total}")
            set_stage("victory_hold")
        return

    if name == "victory_hold":
        if stage_frames() >= 45:
            victory_screen.press_menu()
            set_stage("back")
        return

    if name == "back":
        if stage_frames() >= 30:
            expect("back_to_menu_live",
                   entry.active_pipeline() is None
                   and menu.active and bool(menu.ui_root.enabled)
                   and not victory_screen.visible,
                   f"pipeline={entry.active_pipeline()} "
                   f"menu.active={menu.active} "
                   f"victory_visible={victory_screen.visible}")
            menu.press_scores()
            set_stage("scores")
        return

    if name == "scores":
        if stage_frames() >= 30:
            lines = entry.scores_screen.lines.text
            fr = final_card.get("record") or {}
            expect("menu_responsive_scores_show_run_records",
                   bool(entry.scores_screen.visible)
                   and menu.last_action == "scores"
                   and "LOBBY" in lines and "DATA CENTER" in lines
                   and "PENTHOUSE" in lines
                   and "No takes yet" not in lines,
                   f"visible={entry.scores_screen.visible} lines={lines!r}")
            entry.scores_screen.press_back()
            set_stage("scores_back")
        return

    if name == "scores_back":
        if stage_frames() >= 30:
            expect("scores_back_returns_to_menu",
                   menu.active and bool(menu.ui_root.enabled)
                   and not entry.scores_screen.visible,
                   f"menu.active={menu.active}")
            finish_all()
        return


def update():
    global frames
    dt = min(ursina_time.dt, 1.0 / 30.0)
    if dt <= 0 or done["finished"]:
        return
    frames += 1
    if _time.perf_counter() - started > GLOBAL_TIMEOUT_S:
        expect("global_timeout", False,
               f"stage={stage['name']} cycle_frames={frames}")
        finish_all()
        return
    entry.pump(dt)
    observe()
    cycle_step()


app.run()
sys.exit(0 if not results["failures"] else 1)
