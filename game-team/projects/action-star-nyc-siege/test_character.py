"""Headless QA for the CHARACTER BUILD (Action Star: NYC Siege 3D).

Four parts, all driven through the game's REAL code paths under a
real GL context (Xvfb):

  A. ActionStarModel — part inventory (incl. dual thigh holsters) and
     the 7 poses, each with measurable, distinct part transforms.
  B. In a real GameSession: OTS camera (shoulder offset measured; a
     crosshair-centred target is HIT), wall-run (attach, Y held in a
     tight band, >= 4u along the wall, stick distance in band, camera
     roll <= -10 on a left wall, 1.8s cap detach), and the scripted
     WALL-RUN KILL: +200 through StuntManager with combo math intact
     and the HUD feed entry shown.
  B2. Wall jump (fresh session): Space mid-run -> airborne, apex,
     away-from-wall drift, clean landing, wall-run state cleared —
     and ZERO points for the jump itself.
  C. ANTI-FARM (fresh session, Cyrus's rule): 5 wall-run enter/exit
     cycles (stop / turn-away / wall jump / time-cap / slide exits),
     NO kills, NO shots — the stunt score delta must be EXACTLY 0.
     Points exist only for a kill during a wall-run.
  D. Intro card (separate process, --intro): boots the real
     phase4.game_entry against a throwaway HOME — START shows the
     slate with the fiction, the floor clock is PAUSED and the
     pipeline is not ticked while it is up; dismiss -> clock resumes,
     run plays; a second start auto-dismisses on the slate's hold.

Run:  xvfb-run -a /tmp/ursina-venv/bin/python test_character.py
Exit code 0 = PASS, 1 = FAIL. PROOF lines go to stdout.
"""

import math
import os
import subprocess
import sys
import tempfile
import time as _time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from ursina import Ursina, Vec3, application, camera  # noqa: E402
from ursina import time as ursina_time  # noqa: E402

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
# Part D runs in its own process (game_entry builds its own Ursina app)
# ===========================================================================
def run_intro_part() -> int:
    os.environ["HOME"] = tempfile.mkdtemp(prefix="actionstar-intro-")
    logging_off = ("--quiet-logs" in sys.argv)
    if not logging_off:
        import logging
        logging.basicConfig(level=logging.WARNING)
    from phase4 import game_entry as entry

    menu = entry.menu
    expect("intro_boot_menu_up",
           menu.active and not entry.intro_active()
           and not entry.intro_card.visible,
           f"menu.active={menu.active}")
    menu.press_start()
    pipe = entry.active_pipeline()
    expect("intro_shown_on_start",
           pipe is not None and pipe.session is not None
           and pipe.session.level_num == 1
           and entry.intro_active() and entry.intro_card.visible,
           f"pipeline={pipe is not None} intro={entry.intro_active()}")
    card = entry.intro_card
    expect("intro_carries_fiction",
           "THE ACTION STAR" in card.title.text
           and "ACTION STAR" in card.body.text
           and "Director" in card.body.text
           and "Earn your S" in card.body.text,
           f"title={card.title.text!r}")
    timer = pipe.session.timer
    expect("intro_pauses_floor_clock", timer.is_paused,
           f"is_paused={timer.is_paused}")
    for _ in range(40):
        entry.pump(1.0 / 30.0)
    expect("intro_gates_pipeline",
           pipe.total_frames == 0 and card.visible
           and card.frames >= 30,
           f"pipeline_frames={pipe.total_frames} card_frames={card.frames}")
    entry.dismiss_intro()
    expect("intro_dismiss_resumes",
           not entry.intro_active() and not card.visible
           and not timer.is_paused,
           f"intro_active={entry.intro_active()} paused={timer.is_paused}")
    for _ in range(30):
        entry.pump(1.0 / 30.0)
    expect("intro_run_plays_after_dismiss",
           pipe.total_frames > 0 and timer.elapsed < 1.2,
           f"frames={pipe.total_frames} elapsed={timer.elapsed:.2f}s "
           f"(the ~1.3s slate hold did not eat the take clock)")
    # Second start: the slate must drop on its own (auto-hold).
    entry._back_to_menu()
    menu.press_start()
    pipe2 = entry.active_pipeline()
    expect("intro_reshown_on_second_start",
           pipe2 is not None and entry.intro_active()
           and entry.intro_card.visible, "")
    for _ in range(90):
        entry.pump(0.05)
    expect("intro_auto_dismisses",
           not entry.intro_active() and not entry.intro_card.visible
           and pipe2.session.timer.is_paused is False,
           f"intro_active={entry.intro_active()}")
    for _ in range(10):
        entry.pump(1.0 / 30.0)
    expect("intro_second_run_plays", pipe2.total_frames > 0,
           f"frames={pipe2.total_frames}")
    verdict = "PASS" if not results["failures"] else "FAIL"
    print(f"PROOF intro {verdict}: {results['checks']} checks, "
          f"failures={results['failures']}", flush=True)
    sys.stdout.flush()
    return 0 if not results["failures"] else 1


if "--intro" in sys.argv:
    os._exit(run_intro_part())


# ===========================================================================
# Shared helpers (main process)
# ===========================================================================
def yaw_pitch_to(src: Vec3, dst: Vec3):
    d = dst - src
    yaw = math.degrees(math.atan2(d.x, d.z))
    pitch = math.degrees(math.atan2(d.y, math.hypot(d.x, d.z)))
    return yaw, pitch


def place_guard(guard, pos, patrol):
    guard.entity.position = Vec3(pos.x, 0.9, pos.z)
    guard.patrol_points = [Vec3(p.x, 0.9, p.z) for p in patrol]
    guard._wp_index = 1 % len(patrol)
    guard.state = "patrol"
    guard._last_seen = None
    guard._unseen_for = 0.0


def park_guards_far(session):
    """Move every guard to the far east side: no interference."""
    spots = [(20, 12), (20, -12), (18, 10)]
    for guard, (x, z) in zip(session.guards, spots):
        place_guard(guard, Vec3(x, 0, z),
                    [Vec3(x, 0, z), Vec3(x, 0, z + 0.4)])


app = Ursina(title="Action Star — character QA", vsync=False)

# ===========================================================================
# Part A — the model: inventory + poses
# ===========================================================================
from character_model import POSES, ActionStarModel  # noqa: E402

model = ActionStarModel(spawn=Vec3(0, 0.9, 0))
EXPECTED_PARTS = {
    "root", "rig", "torso", "chest", "chest_plate", "belt", "head_grp",
    "head", "hair", "arm_l", "arm_r", "upperarm_l", "upperarm_r",
    "hand_l", "hand_r", "gun", "leg_l", "leg_r", "thigh_l", "thigh_r",
    "boot_l", "boot_r", "holster_l", "holster_r", "holster_grip_l",
    "holster_grip_r",
}
missing = EXPECTED_PARTS - set(model.parts)
expect("model_part_inventory", not missing,
       f"{len(model.parts)} parts, missing={sorted(missing)}")
expect("model_dual_thigh_holsters",
       model.parts["holster_l"].parent is model.leg_l
       and model.parts["holster_r"].parent is model.leg_r
       and model.parts["holster_l"].position.x < 0
       and model.parts["holster_r"].position.x > 0,
       "one holster box strapped to each thigh, on the outer side")
expect("model_dark_tactical_look",
       model.parts["hand_l"].color == model.parts["hand_r"].color
       and model.parts["gun"].parent is model.arm_r,
       "gloved hands + pistol in the right hand")


def pose_signature(m):
    return (
        round(m.rig.position.y, 3), round(m.rig.rotation.x, 2),
        round(m.rig.rotation.z, 2), round(m.torso.rotation.y, 2),
        round(m.arm_r.rotation.x, 2), round(m.arm_l.rotation.x, 2),
        round(m.leg_l.rotation.x, 2), round(m.leg_r.rotation.x, 2),
    )


model.set_aim_pitch(0.0)
signatures = {}
for pose in POSES:
    model.set_pose(pose)
    signatures[pose] = pose_signature(model)
    expect(f"model_pose_applies_{pose.lower()}", model.pose == pose, "")
expect("model_poses_all_distinct",
       len(set(signatures.values())) == len(POSES),
       f"signatures={ {k: v for k, v in signatures.items()} }")
expect("model_pose_aim_arm_raised", signatures["AIM"][4] <= -80.0,
       f"arm_r.rotation_x={signatures['AIM'][4]}")
expect("model_pose_slide_low_pitched",
       signatures["SLIDE"][0] <= -0.4 and signatures["SLIDE"][1] <= -25.0,
       f"rig_y={signatures['SLIDE'][0]} rig_pitch={signatures['SLIDE'][1]}")
expect("model_pose_melee_twist_strike",
       signatures["MELEE"][3] >= 20.0 and signatures["MELEE"][4] <= -130.0,
       f"torso_yaw={signatures['MELEE'][3]} arm_r={signatures['MELEE'][4]}")
model.set_pose("WALLRUN")
model.set_wallrun_side(1)
bank_right = model.rig.rotation.z
model.set_wallrun_side(-1)
bank_left = model.rig.rotation.z
expect("model_pose_wallrun_banks_toward_wall",
       bank_right <= -12.0 and bank_left >= 12.0,
       f"side+1 -> {bank_right}, side-1 -> {bank_left} (sign flips)")
expect("model_pose_dodge_lean",
       signatures["DODGE"][2] == -14.0, f"rig_roll={signatures['DODGE'][2]}")
model.set_pose("IDLE")

# ===========================================================================
# Parts B / B2 / C — real sessions, driven by the phase machine
# ===========================================================================
from level1.main import GameSession  # noqa: E402
from level1.player_controller_3d import PlayerInput  # noqa: E402

DT = 1.0 / 30.0
started = _time.perf_counter()
GLOBAL_TIMEOUT_S = 300.0
frames = 0
# Accumulated TICK time (the controller's own clock domain). Span
# measurements use this, never the wall clock: under software
# rendering the rendered frame rate lags the tick rate, so wall
# spans would overstate the controller's 1.8s cap.
SIM = {"t": 0.0}
phase = "b_ots_setup"
phase_started = _time.perf_counter()
P = {}


def set_phase(name):
    global phase, phase_started
    phase = name
    phase_started = _time.perf_counter()
    P.clear()
    print(f"PROOF phase -> {name}", flush=True)


def phase_elapsed():
    return _time.perf_counter() - phase_started


def timed_out(limit):
    return phase_elapsed() > limit


# --- Part B session: OTS + wall-run + kill ---------------------------------
s2 = GameSession()
p2 = s2.player


def ph_b_ots_setup():
    expect("controller_body_is_model",
           isinstance(p2.model, ActionStarModel)
           and p2.entity is p2.model.root
           and p2.camera_rig is s2.level.camera_rig,
           "player entity is the ActionStarModel root; rig wired")
    rig = s2.level.camera_rig
    expect("ots_shoulder_offset_configured", rig.shoulder >= 1.0,
           f"shoulder={rig.shoulder}")
    park_guards_far(s2)
    place_guard(s2.guards[2], Vec3(0, 0, 6),
                [Vec3(0, 0, 6), Vec3(0.3, 0, 6)])
    p2.entity.position = Vec3(0, 0.9, -2)
    rig.update(p2.position, 0.0, 0.0)
    offset = camera.position - p2.position
    expect("ots_camera_offset_right_and_up",
           offset.x > 0.8 and offset.y > 1.5,
           f"offset=({offset.x:.2f}, {offset.y:.2f}, {offset.z:.2f}) "
           f"for a north-facing player (right = +x)")
    set_phase("b_ots_fire")
    return PlayerInput()


def ph_b_ots_fire():
    g3 = s2.guards[2]
    cam = camera.position
    yaw = math.degrees(math.atan2(g3.position.x - cam.x,
                                  g3.position.z - cam.z))
    inp = PlayerInput(aim_yaw=yaw, aim_pitch=-2.0, shoot=True)
    if p2.last_shot["kind"] == "guard" and g3.hp < 100.0:
        expect("ots_centered_target_hit", True,
               f"crosshair-centred guard hit: hp={g3.hp:.0f}, "
               f"shot={p2.last_shot}")
        set_phase("b_wr_setup")
    elif timed_out(4):
        expect("ots_centered_target_hit", False,
               f"last_shot={p2.last_shot} g3_hp={g3.hp:.0f}")
        set_phase("b_wr_setup")
    return inp


def ph_b_wr_setup():
    park_guards_far(s2)
    place_guard(s2.guards[1], Vec3(-18.5, 0, -2),
                [Vec3(-18.5, 0, -2), Vec3(-18.3, 0, -2)])
    p2.hp = 100.0
    p2.entity.position = Vec3(-21.15, 0.9, -11.5)
    set_phase("b_wr_run")
    return PlayerInput()


def ph_b_wr_run():
    if "samples" not in P:   # set_phase() clears P, so init lazily here
        P.update(samples=[], spans=[], span_start=None, was_wr=False,
                 kill_tick_done=False, feed_seen=False, transitions=0,
                 kill_events=None)
    g2 = s2.guards[1]
    wr = p2.wall_running
    now = SIM["t"]
    if wr and not P["was_wr"]:
        P["span_start"] = now
    if not wr and P["was_wr"] and P["span_start"] is not None:
        P["spans"].append(now - P["span_start"])
        P["span_start"] = None
        P["transitions"] += 1
    P["was_wr"] = wr
    if wr and p2.position.y >= 1.4:
        gap = s2.level.world.circle_gap(p2.position.x, p2.position.z,
                                        p2.radius)
        P["samples"].append((now, p2.position.y, gap,
                             s2.level.camera_rig.roll, p2.position.z))
    if not g2.alive and not P["kill_tick_done"]:
        P["kill_tick_done"] = True
        events = [e for e in s2.stunt.events
                  if e.action_type == "wall_run_kill"]
        P["kill_events"] = events
        if any("WALL-RUN KILL" in t for t in s2.hud.feed_texts()):
            P["feed_seen"] = True
    if P.get("feed_seen") is False and P["kill_tick_done"]:
        if any("WALL-RUN KILL" in t for t in s2.hud.feed_texts()):
            P["feed_seen"] = True
    # Aim at G2 and fire only while attached (the kill must be a
    # wall-run kill); before attach / after the kill, just run north.
    if wr and g2.alive:
        yaw, pitch = yaw_pitch_to(p2.position + Vec3(0, 0.5, 0),
                                  g2.position + Vec3(0, 0.35, 0))
        inp = PlayerInput(move=Vec3(0, 0, 1), aim_yaw=yaw,
                          aim_pitch=pitch, shoot=True)
    else:
        inp = PlayerInput(move=Vec3(0, 0, 1), aim_yaw=0.0)
    done_kill = P["kill_tick_done"]
    span_closed_after_kill = done_kill and not wr and P["transitions"] >= 1
    if (done_kill and span_closed_after_kill) or timed_out(16):
        _verify_wall_run()
        set_phase("b_wr_settle")
    return inp


def _verify_wall_run():
    samples = P["samples"]
    expect("wallrun_attached", len(samples) > 0 and len(P["spans"]) >= 1,
           f"spans={[round(s, 2) for s in P['spans']]}")
    if samples:
        span_t = samples[-1][0] - samples[0][0]
        ys = [s[1] for s in samples]
        gaps = [s[2] for s in samples]
        rolls = [s[3] for s in samples]
        travel = samples[-1][4] - samples[0][4]
        expect("wallrun_hold_duration", span_t >= 1.0,
               f"settled attached span={span_t:.2f}s")
        expect("wallrun_y_held_tight_band", max(ys) - min(ys) <= 0.12,
               f"y in [{min(ys):.3f}, {max(ys):.3f}] while attached")
        expect("wallrun_travel_along_wall", travel >= 4.0,
               f"z travel while attached={travel:.2f}u")
        expect("wallrun_stick_distance_band",
               all(0.15 <= g <= 0.6 for g in gaps),
               f"wall gap in [{min(gaps):.3f}, {max(gaps):.3f}] "
               f"(stick target 0.35)")
        expect("wallrun_camera_roll_left_wall",
               min(rolls) <= -10.0,
               f"roll reached {min(rolls):.1f} deg (left wall -> -15)")
    if P["spans"]:
        expect("wallrun_time_cap_1_8s", max(P["spans"]) <= 2.0
               and max(P["spans"]) >= 1.6,
               f"longest attached span={max(P['spans']):.2f}s of tick "
               f"time (cap 1.8)")
    events = P.get("kill_events") or []
    expect("wallrun_kill_registered_200",
           len(events) == 1 and events[0].base_points == 200,
           f"events={[(e.action_type, e.base_points) for e in s2.stunt.events]}")
    if events:
        ev = events[0]
        total = sum(e.points_awarded for e in s2.stunt.events) \
            + sum(b.bonus_points for b in s2.stunt.multi_kill_bonuses)
        expect("wallrun_kill_combo_math_intact",
               ev.points_awarded == int(200 * ev.multiplier_applied)
               and s2.stunt.current_score == total,
               f"awarded={ev.points_awarded} x{ev.multiplier_applied} "
               f"score={s2.stunt.current_score} recomputed={total}")
    expect("wallrun_kill_hud_feed", P["feed_seen"],
           "'+200 PTS ⚡ WALL-RUN KILL' appeared in the HUD feed")


def ph_b_wr_settle():
    inp = PlayerInput()
    if phase_elapsed() > 1.2:
        roll = s2.level.camera_rig.roll
        expect("wallrun_camera_roll_recovers", abs(roll) < 3.0,
               f"roll={roll:.2f} deg 1.2s after detach")
        expect("wallrun_height_recovers",
               not p2.wall_running and p2.position.y < 1.05,
               f"y={p2.position.y:.2f}")
        set_phase("b2_setup")
    return inp


# --- Part B2 session: the wall jump -----------------------------------------
s3 = GameSession()
p3 = s3.player


def ph_b2_setup():
    park_guards_far(s3)
    p3.entity.position = Vec3(-21.15, 0.9, -8)
    set_phase("b2_run")
    return PlayerInput()


def ph_b2_run():
    if "jumped" not in P:
        P.update(jumped=False, jump_x=None, max_y=0.0, saw_air=False,
                 landed=False)
    inp = PlayerInput(move=Vec3(0, 0, 1), aim_yaw=0.0)
    if p3.wall_running and not P["jumped"]:
        P["jumped"] = True
        P["jump_x"] = p3.position.x
        P["jump_at"] = _time.perf_counter()
        inp.jump = True
    if P["jumped"]:
        P["max_y"] = max(P["max_y"], p3.position.y)
        if p3.airborne:
            P["saw_air"] = True
        if P["saw_air"] and not p3.airborne and not p3.wall_running:
            P["landed"] = True
    if P["landed"] or timed_out(8):
        dx = (p3.position.x - P["jump_x"]) if P["jump_x"] is not None \
            else 0.0
        expect("walljump_executed_airborne",
               P["jumped"] and P["saw_air"] and P["landed"],
               f"jumped={P['jumped']} airborne_seen={P['saw_air']} "
               f"landed={P['landed']}")
        expect("walljump_apex_and_away_drift",
               P["max_y"] >= 1.95 and dx >= 1.2,
               f"max_y={P['max_y']:.2f} away_drift={dx:.2f}u")
        expect("walljump_clears_state_and_scores_nothing",
               not p3.wall_running and not p3.airborne
               and abs(p3.position.y - 0.9) < 0.01
               and s3.stunt.current_score == 0
               and len(s3.stunt.events) == 0,
               f"y={p3.position.y:.2f} score={s3.stunt.current_score} "
               f"events={len(s3.stunt.events)}")
        set_phase("c_setup")
    return inp


# --- Part C session: ANTI-FARM ----------------------------------------------
s4 = GameSession()
p4 = s4.player
FARM_MODES = ["stop", "away", "jump", "cap", "slide"]


def ph_c_setup():
    park_guards_far(s4)
    _farm_reset_player()
    set_phase("c_run")
    return PlayerInput()


def _farm_reset_player():
    p4.entity.position = Vec3(-21.15, 0.9, -12.5)
    p4.hp = 100.0


def ph_c_run():
    if "cycle" not in P:
        P.update(cycle=0, sub="enter", entries=0, exits=0, was_wr=False,
                 span_start=None, cap_span=0.0, jump_exit_seen=False,
                 score0=s4.stunt.current_score, jump_pressed=False,
                 slide_pressed=False, settle_at=None)
    wr = p4.wall_running
    now = SIM["t"]
    if wr and not P["was_wr"]:
        P["entries"] += 1
        P["span_start"] = now
        P["sub"] = "exit"
    if not wr and P["was_wr"]:
        P["exits"] += 1
        if P["span_start"] is not None:
            span = now - P["span_start"]
            if FARM_MODES[P["cycle"]] == "cap":
                P["cap_span"] = span
            P["span_start"] = None
        P["sub"] = "settle"
        P["settle_at"] = now
    P["was_wr"] = wr
    if p4.airborne and FARM_MODES[P["cycle"]] == "jump" \
            and P["sub"] in ("exit", "settle"):
        P["jump_exit_seen"] = True

    mode = FARM_MODES[P["cycle"]]
    sub = P["sub"]
    inp = PlayerInput(aim_yaw=0.0)
    if sub == "enter":
        inp.move = Vec3(0, 0, 1)
        if timed_out(30):
            expect("antifarm_cycles_completed", False,
                   f"stuck entering cycle {P['cycle']}")
            set_phase("finish")
    elif sub == "exit":
        if mode == "stop":
            inp.move = Vec3(0, 0, 0)
        elif mode == "away":
            inp.move = Vec3(1, 0, 0)
        elif mode == "jump":
            if not P.get("jump_pressed"):
                P["jump_pressed"] = True
                inp.move = Vec3(0, 0, 1)
                inp.jump = True
            else:
                inp.move = Vec3(0, 0, 0)
            if p4.airborne:
                P["jump_exit_seen"] = True
        elif mode == "cap":
            inp.move = Vec3(0, 0, 1)
        elif mode == "slide":
            if not P.get("slide_pressed"):
                P["slide_pressed"] = True
                inp.move = Vec3(0, 0, 1)
                inp.slide = True
            else:
                inp.move = Vec3(0, 0, 0)
    elif sub == "settle":
        inp.move = Vec3(0, 0, 0)
        settled = (not p4.airborne
                   and now - P.get("settle_at", now) > 0.4)
        if settled:
            P["cycle"] += 1
            P["jump_pressed"] = False
            P["slide_pressed"] = False
            if P["cycle"] >= len(FARM_MODES):
                _verify_antifarm()
                set_phase("finish")
                return inp
            _farm_reset_player()
            P["sub"] = "enter"
    return inp


def _verify_antifarm():
    expect("antifarm_five_cycles",
           P["entries"] >= 5 and P["exits"] >= 5,
           f"entries={P['entries']} exits={P['exits']} "
           f"modes={FARM_MODES}")
    expect("antifarm_walljump_exit_seen", P["jump_exit_seen"],
           "one exit was a wall jump (airborne observed)")
    expect("antifarm_cap_exit_span", 1.6 <= P["cap_span"] <= 2.0,
           f"cap-exit attached span={P['cap_span']:.2f}s of tick time")
    delta = s4.stunt.current_score - P["score0"]
    expect("antifarm_score_delta_exactly_zero",
           delta == 0 and len(s4.stunt.events) == 0
           and p4.shots_fired == 0,
           f"score {P['score0']} -> {s4.stunt.current_score} "
           f"(delta {delta}), events={len(s4.stunt.events)}, "
           f"shots={p4.shots_fired} — no points for entering, "
           f"exiting or wall-jumping; kills only")


PHASES = {
    "b_ots_setup": (ph_b_ots_setup, s2),
    "b_ots_fire": (ph_b_ots_fire, s2),
    "b_wr_setup": (ph_b_wr_setup, s2),
    "b_wr_run": (ph_b_wr_run, s2),
    "b_wr_settle": (ph_b_wr_settle, s2),
    "b2_setup": (ph_b2_setup, s3),
    "b2_run": (ph_b2_run, s3),
    "c_setup": (ph_c_setup, s4),
    "c_run": (ph_c_run, s4),
}

done = {"finished": False}


def finish_all():
    if done["finished"]:
        return
    done["finished"] = True
    # Part D — the intro card, in its own process.
    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--intro"],
        capture_output=True, text=True, env=env, timeout=240)
    for line in proc.stdout.splitlines():
        if "PROOF" in line:
            print(f"[intro] {line}", flush=True)
    expect("intro_card_part_passed", proc.returncode == 0,
           f"returncode={proc.returncode} "
           f"stderr_tail={proc.stderr.strip().splitlines()[-3:]}")
    elapsed = _time.perf_counter() - started
    print(f"PROOF character frames={frames} elapsed={elapsed:.2f}s "
          f"(sandbox software rendering)", flush=True)
    verdict = "PASS" if not results["failures"] else "FAIL"
    print(f"PROOF character {verdict}: {results['checks']} checks, "
          f"{len(results['failures'])} failures: {results['failures']}",
          flush=True)
    sys.stdout.flush()
    application.quit()


def update():
    global frames
    dt = min(ursina_time.dt, DT)
    if dt <= 0 or done["finished"]:
        return
    frames += 1
    SIM["t"] += dt
    if _time.perf_counter() - started > GLOBAL_TIMEOUT_S:
        expect("global_timeout", False, f"phase={phase}")
        finish_all()
        return
    if phase == "finish":
        finish_all()
        return
    handler, session = PHASES[phase]
    inp = handler()
    if not done["finished"] and phase in PHASES:
        PHASES[phase][1].tick(dt, inp)


app.run()
sys.exit(0 if not results["failures"] else 1)
