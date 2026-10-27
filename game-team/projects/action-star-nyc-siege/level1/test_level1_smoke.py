"""Headless QA smoke test for Level 1: Tower Lobby (Ursina).

Builds the REAL GameSession (the same assembly main.py runs for a human)
under a real GL context (Xvfb) and drives it with a scripted autopilot
through every Stage-2 mechanic:

  * bullet vs COLUMN and bullet vs DESK — hitscan blocked by cover, the
    guard behind the cover unharmed (Cyrus acceptance gate 2);
  * player vs DESK and player vs COLUMN — movement blocked, no clipping
    (gate 2, with position / clearance evidence);
  * shooting kill on guard 1, melee kill on guard 2 (A Takedown stunt);
  * slide (distance evidence vs walking);
  * Bullet Time — world time-scale 0.3 asserted, charge drain asserted,
    a guard bullet produces a Bullet Dodge or an HP drop;
  * FPS gate (Cyrus gate 1): average FPS in a normal-speed window vs a
    Bullet Time window of the SAME run, with the % difference;
  * elevator WIN — the final report card is verified field by field
    against the live HUD/logic state, incl. S_time recomputed from the
    run's own T_actual (Cyrus gate 3).

Run:  xvfb-run -a /tmp/ursina-venv/bin/python level1/test_level1_smoke.py
Exit code 0 = PASS, 1 = FAIL. PROOF lines go to stdout.
"""

import math
import os
import sys
import time as _time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEVEL1_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, LEVEL1_DIR)

from ursina import Ursina, Vec3, application  # noqa: E402
from ursina import time as ursina_time  # noqa: E402

from level1.main import TARGET_TIME_S, GameSession  # noqa: E402
from level1.player_controller_3d import PlayerInput  # noqa: E402
from logic import take_rating  # noqa: E402

app = Ursina(title="Action Star — Level 1 smoke", vsync=False)
session = GameSession()
player = session.player
stunt = session.stunt
hud = session.hud
level = session.level
g1, g2, g3 = session.guards

results = {"failures": [], "checks": 0}
frames = 0
started = _time.perf_counter()
GLOBAL_TIMEOUT_S = 170.0


def check(name, ok, detail=""):
    results["checks"] += 1
    line = f"PROOF check {name}: {'OK' if ok else 'FAIL'} {detail}".rstrip()
    print(line, flush=True)
    if not ok:
        results["failures"].append(name)


def expect(name, ok, detail=""):
    check(name, bool(ok), detail)


# ---------------------------------------------------------------------------
# Autopilot helpers
# ---------------------------------------------------------------------------
def yaw_pitch_to(src: Vec3, dst: Vec3):
    d = dst - src
    yaw = math.degrees(math.atan2(d.x, d.z))
    pitch = math.degrees(math.atan2(d.y, math.hypot(d.x, d.z)))
    return yaw, pitch


def goto_input(target: Vec3, aim_point=None):
    """Input that runs the player toward `target`; True when arrived."""
    rel = Vec3(target.x - player.position.x, 0, target.z - player.position.z)
    dist = rel.length()
    yaw, pitch = yaw_pitch_to(player.position, aim_point or target)
    inp = PlayerInput(move=rel.normalized() if dist > 0.05 else Vec3(0, 0, 0),
                      aim_yaw=yaw, aim_pitch=pitch)
    return inp, dist


def nav_input(points):
    """Waypoint-following input: steers through `points` in order
    (routes around furniture instead of grinding along it). Returns
    (input, arrived_at_final_point). Waypoint queue lives in P['wps']
    and is initialised on first call after a phase change."""
    if "wps" not in P:
        P["wps"] = list(points)
    while P["wps"]:
        target = P["wps"][0]
        rel = Vec3(target.x - player.position.x, 0,
                   target.z - player.position.z)
        if rel.length() < 0.6:
            P["wps"].pop(0)
            continue
        inp, _ = goto_input(target)
        return inp, False
    inp, _ = goto_input(points[-1])
    return inp, True


def solid_by_name(name):
    for s in level.world.solids:
        if s.name == name:
            return s
    raise KeyError(name)


def gap_to_solid(solid, pos, radius):
    nx = max(solid.min_x, min(pos.x, solid.max_x))
    nz = max(solid.min_z, min(pos.z, solid.max_z))
    return math.hypot(pos.x - nx, pos.z - nz) - radius


def place_guard(guard, pos, patrol):
    guard.entity.position = Vec3(pos.x, 0.9, pos.z)
    guard.patrol_points = [Vec3(p.x, 0.9, p.z) for p in patrol]
    guard._wp_index = 1 % len(patrol)
    guard.state = "patrol"
    guard._last_seen = None
    guard._unseen_for = 0.0


G3_PATROL = [Vec3(-5, 0, 11), Vec3(5, 0, 11)]

# ---------------------------------------------------------------------------
# Phase machine
# ---------------------------------------------------------------------------
phase = "player_desk_push"
phase_started = _time.perf_counter()
P = {}   # per-phase scratch data


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


# ---------------------------------------------------------------------------
# Phases. Each returns the PlayerInput for this tick; transitions call
# set_phase / finish.
# ---------------------------------------------------------------------------
def ph_bullet_column_goto():
    inp, arrived = nav_input([Vec3(-4.5, 0, -3), Vec3(-3, 0, 0)])
    if arrived or timed_out(14):
        place_guard(g3, Vec3(-14, 0, 0), [Vec3(-14, 0, 0), Vec3(-14, 0, 0.5)])
        set_phase("bullet_column_fire")
    return inp


def ph_bullet_column_fire():
    if "shots" not in P:
        P.update(shots=[], last_count=player.shots_fired, cover_hit=None)
    yaw, pitch = yaw_pitch_to(player.position + Vec3(0, 0.5, 0),
                              g3.position + Vec3(0, 0.35, 0))
    inp = PlayerInput(move=Vec3(0, 0, 0), aim_yaw=yaw, aim_pitch=pitch,
                      shoot=True)
    if player.shots_fired > P["last_count"]:
        P["last_count"] = player.shots_fired
        shot = dict(player.last_shot)
        P["shots"].append(shot)
        if shot["kind"] == "cover" and str(shot["solid"]).startswith("column"):
            P["cover_hit"] = shot
    if (P["cover_hit"] and len(P["shots"]) >= 3) or len(P["shots"]) >= 6 \
            or timed_out(8):
        hit = P["cover_hit"]
        expect("bullet_vs_column_blocked", hit is not None,
               f"shots={[ (s['kind'], s['solid'], round(s['distance'],2)) for s in P['shots'] ]}")
        if hit:
            print(f"PROOF evidence bullet_vs_column: impact on "
                  f"{hit['solid']} at {hit['distance']:.2f}u from muzzle; "
                  f"guard G3 behind it at ~11.0u, HP={g3.hp:.0f}", flush=True)
        expect("bullet_vs_column_guard_unharmed", g3.hp >= 100.0,
               f"g3_hp={g3.hp:.0f}")
        set_phase("bullet_desk_goto")
    return inp


def ph_bullet_desk_goto():
    inp, arrived = nav_input([Vec3(-4.5, 0, -4), Vec3(-4.5, 0, -10.5),
                              Vec3(0, 0, -12.3)])
    if arrived:
        place_guard(g3, Vec3(0, 0, -3), [Vec3(0, 0, -3), Vec3(0.4, 0, -3)])
        set_phase("bullet_desk_fire")
    elif timed_out(16):
        # Never reached the firing position: fail this setup honestly and
        # skip the fire phase (no teleport — the guard stays put).
        expect("bullet_vs_desk_blocked", False,
               "autopilot never reached the firing position south of the desk")
        expect("bullet_vs_desk_guard_unharmed", g3.hp >= 100.0,
               f"g3_hp={g3.hp:.0f}")
        place_guard(g3, G3_PATROL[0], G3_PATROL)
        set_phase("shoot_g1")
    return inp


def ph_bullet_desk_fire():
    if "shots" not in P:
        P.update(shots=[], last_count=player.shots_fired, cover_hit=None)
    # Aim at the guard's LOWER BODY — the part the 1.15u-high desk actually
    # covers. (A chest-height ray at 1.40->1.25 physically clears a
    # waist-high desk; run 2 proved that by hitting the guard over it.
    # The cover question is whether shots at the covered part are blocked.)
    yaw, pitch = yaw_pitch_to(player.position + Vec3(0, 0.5, 0),
                              g3.position + Vec3(0, -0.25, 0))
    inp = PlayerInput(move=Vec3(0, 0, 0), aim_yaw=yaw, aim_pitch=pitch,
                      shoot=True)
    if player.shots_fired > P["last_count"]:
        P["last_count"] = player.shots_fired
        shot = dict(player.last_shot)
        P["shots"].append(shot)
        if shot["kind"] == "cover" and shot["solid"] == "reception_desk":
            P["cover_hit"] = shot
    if (P["cover_hit"] and len(P["shots"]) >= 3) or len(P["shots"]) >= 6 \
            or timed_out(8):
        hit = P["cover_hit"]
        expect("bullet_vs_desk_blocked", hit is not None,
               f"shots={[ (s['kind'], s['solid'], round(s['distance'],2)) for s in P['shots'] ]}")
        if hit:
            print(f"PROOF evidence bullet_vs_desk: impact on "
                  f"{hit['solid']} at {hit['distance']:.2f}u from muzzle; "
                  f"guard G3 behind it at ~9.3u, HP={g3.hp:.0f}", flush=True)
        expect("bullet_vs_desk_guard_unharmed", g3.hp >= 100.0,
               f"g3_hp={g3.hp:.0f}")
        place_guard(g3, G3_PATROL[0], G3_PATROL)   # restore the elevator guard
        set_phase("shoot_g1")
    return inp


def ph_player_desk_push():
    desk = solid_by_name("reception_desk")
    if "min_gap" not in P:
        P.update(min_gap=999.0, late_moves=[], last_pos=player.position)
    inp, _ = goto_input(Vec3(0, 0, -4))
    gap = gap_to_solid(desk, player.position, player.radius)
    P["min_gap"] = min(P["min_gap"], gap)
    # "Stopped" is judged only AFTER first contact (+0.3s settle), so
    # approach frames and dt spikes cannot pollute the measurement.
    # Contact = clearance within one movement step (<= ~0.28u).
    if "contact_at" not in P and gap < 0.30:
        P["contact_at"] = phase_elapsed()
    if "contact_at" in P and phase_elapsed() > P["contact_at"] + 0.25:
        P["late_moves"].append(
            (player.position - P["last_pos"]).length())
    P["last_pos"] = player.position
    if ("contact_at" in P and phase_elapsed() > P["contact_at"] + 0.8) \
            or timed_out(9):
        z = player.position.z
        expect("player_vs_desk_blocked", -8.85 <= z <= -8.3,
               f"final_z={z:.2f} (desk face at -8.10, radius 0.45)")
        expect("player_vs_desk_no_clip", P["min_gap"] >= -0.02,
               f"min_clearance={P['min_gap']:.3f}u")
        recent = max(P["late_moves"][-10:]) if P["late_moves"] else 999
        expect("player_vs_desk_stopped", recent < 0.05,
               f"max move per frame while pushing={recent:.3f}u")
        print(f"PROOF evidence player_vs_desk: stopped at z={z:.2f}, "
              f"desk face z=-8.10, min clearance {P['min_gap']:.3f}u",
              flush=True)
        set_phase("player_column_goto")
    return inp


def ph_player_column_goto():
    inp, arrived = nav_input([Vec3(-4.8, 0, -8.6), Vec3(-4.5, 0, -8)])
    if arrived or timed_out(10):
        set_phase("player_column_push")
    return inp


def ph_player_column_push():
    column = solid_by_name("column_-8_-8")
    if "min_gap" not in P:
        P.update(min_gap=999.0, late_moves=[], last_pos=player.position)
    inp, _ = goto_input(Vec3(-12, 0, -8))
    gap = gap_to_solid(column, player.position, player.radius)
    P["min_gap"] = min(P["min_gap"], gap)
    if "contact_at" not in P and gap < 0.30:
        P["contact_at"] = phase_elapsed()
    if "contact_at" in P and phase_elapsed() > P["contact_at"] + 0.25:
        P["late_moves"].append(
            (player.position - P["last_pos"]).length())
    P["last_pos"] = player.position
    if ("contact_at" in P and phase_elapsed() > P["contact_at"] + 0.8) \
            or timed_out(9):
        x = player.position.x
        expect("player_vs_column_blocked", -7.0 <= x <= -6.45,
               f"final_x={x:.2f} (column face at -7.20, radius 0.45)")
        expect("player_vs_column_no_clip", P["min_gap"] >= -0.02,
               f"min_clearance={P['min_gap']:.3f}u")
        recent = max(P["late_moves"][-10:]) if P["late_moves"] else 999
        expect("player_vs_column_stopped", recent < 0.05,
               f"max move per frame while pushing={recent:.3f}u")
        print(f"PROOF evidence player_vs_column: stopped at x={x:.2f}, "
              f"column face x=-7.20, min clearance {P['min_gap']:.3f}u",
              flush=True)
        set_phase("bullet_column_goto")
    return inp


def ph_shoot_g1():
    if "start_shots" not in P:
        P.update(start_shots=player.shots_fired,
                 start_tracers=player.tracers_spawned)
    # Orbit to the OPEN side of G1: the point 8u from G1 toward the
    # lobby centre, recomputed every tick. A fixed band lets a guard
    # keep a column between itself and the player indefinitely
    # (run 8: 16s, zero damage); the orbit cannot be covered for long.
    to_center = Vec3(-g1.position.x, 0, -g1.position.z)
    if to_center.length() < 0.1:
        to_center = Vec3(0, 0, -1)
    standoff = g1.position + to_center.normalized() * 8.0
    rel = Vec3(standoff.x - player.position.x, 0,
               standoff.z - player.position.z)
    move = rel.normalized() if rel.length() > 0.9 else Vec3(0, 0, 0)
    yaw, pitch = yaw_pitch_to(player.position + Vec3(0, 0.5, 0),
                              g1.position + Vec3(0, 0.35, 0))
    inp = PlayerInput(move=move, aim_yaw=yaw, aim_pitch=pitch, shoot=True)
    if not g1.alive:
        expect("shooting_kills_guard1", True,
               f"shots={player.shots_fired - P['start_shots']}")
        expect("tracer_visible", player.tracers_spawned > P["start_tracers"],
               f"tracers={player.tracers_spawned - P['start_tracers']}")
        set_phase("melee_g2")
    elif timed_out(20):
        expect("shooting_kills_guard1", False,
               f"g1_hp={g1.hp:.0f} after 20s")
        set_phase("melee_g2")
    return inp


def ph_melee_g2():
    rel = g2.position - player.position
    rel.y = 0
    dist = rel.length()
    yaw, pitch = yaw_pitch_to(player.position, g2.position)
    move = rel.normalized() if dist > 1.6 else Vec3(0, 0, 0)
    inp = PlayerInput(move=move, aim_yaw=yaw, aim_pitch=0.0,
                      melee=dist < 2.2)
    if not g2.alive:
        actions = [e.action_type for e in stunt.events]
        expect("melee_kills_guard2", True, f"events={actions}")
        expect("air_takedown_registered", "air_takedown" in actions,
               f"events={actions}")
        set_phase("slide_goto")
    elif timed_out(16):
        expect("melee_kills_guard2", False, f"g2_hp={g2.hp:.0f} after 16s")
        set_phase("slide_goto")
    return inp


def ph_slide_goto():
    inp, arrived = nav_input([Vec3(-8, 0, 2)])
    if arrived or timed_out(14):
        set_phase("slide_run")
    return inp


def ph_slide_run():
    if "state" not in P:
        P.update(state="accelerate", t0=phase_elapsed())
    move = Vec3(1, 0, 0)   # east along the clear z=2 lane — NOT north:
    # a northward slide from mid-lobby overshoots into the elevator
    # goal zone and ends the stage early (found in run 7/8 forensics)
    slide_press = False
    if P["state"] == "accelerate" and phase_elapsed() - P["t0"] > 0.3:
        slide_press = True
        P["state"] = "sliding"
        P["start_pos"] = None
    if P["state"] == "sliding":
        if player.is_sliding and P["start_pos"] is None:
            P["start_pos"] = Vec3(player.position.x, 0, player.position.z)
            P["saw_slide"] = True
        if not player.is_sliding and P.get("start_pos") is not None:
            dist = (player.position - P["start_pos"]).length()
            walk_same_time = 7.5 * 0.65
            expect("slide_executed", P.get("saw_slide", False),
                   f"slide_distance={dist:.2f}u")
            expect("slide_faster_than_walking", dist > walk_same_time * 1.12,
                   f"slide={dist:.2f}u vs walking {walk_same_time:.2f}u "
                   f"in the same 0.65s")
            set_phase("arena_goto")
    if timed_out(7) and phase != "arena_goto":
        expect("slide_executed", False, "slide never engaged")
        set_phase("arena_goto")
    return PlayerInput(move=move, aim_yaw=0.0, slide=slide_press)


def ph_arena_goto():
    inp, dist = goto_input(Vec3(0, 0, 8.5))
    if dist < 0.6 or timed_out(12):
        set_phase("dodge")
    return inp


def ph_dodge():
    """Bullet-Dodge choreography: wait at NORMAL speed until the elevator
    guard actually fires, then trigger Bullet Time (the in-flight bullet
    slows to 0.3x) and sidestep ~1.3u — the bullet must pass within the
    1.7u dodge radius without hitting (or, failing the sidestep, hit)."""
    if "stage" not in P:
        P.update(stage="wait_fire", spawn0=session.bullets.total_spawned,
                 hp0=player.hp,
                 dodges0=len([e for e in stunt.events
                              if e.action_type == "bullet_dodge"]))
    yaw, _ = yaw_pitch_to(player.position, g3.position)
    inp = PlayerInput(move=Vec3(0, 0, 0), aim_yaw=yaw)

    if P["stage"] == "wait_fire":
        if session.bullets.total_spawned > P["spawn0"]:
            P["stage"] = "evade"
            P["evade_until"] = phase_elapsed() + 0.18
            inp.bullet_time = True
            inp.move = Vec3(1.0, 0, 0)
        elif timed_out(14):
            expect("guard_bullet_dodge_or_hit", False,
                   "guard never fired during the dodge setup")
            set_phase("fps_normal")
        return inp

    if P["stage"] == "evade":
        inp.move = Vec3(1.0, 0, 0)
        if phase_elapsed() >= P["evade_until"]:
            P["stage"] = "watch"
            P["watch_until"] = phase_elapsed() + 2.5
        return inp

    # watch: stand still in Bullet Time while the slowed bullet passes
    dodges = len([e for e in stunt.events
                  if e.action_type == "bullet_dodge"])
    if dodges > P["dodges0"] or player.hp < P["hp0"]:
        expect("guard_bullet_dodge_or_hit", True,
               f"dodges {P['dodges0']}->{dodges}, "
               f"hp {P['hp0']:.0f}->{player.hp:.0f}, "
               f"bullet_time={player.bt_active}")
        inp.bullet_time = True   # toggle BT back off for the FPS windows
        set_phase("fps_normal")
    elif phase_elapsed() >= P["watch_until"] or timed_out(20):
        expect("guard_bullet_dodge_or_hit", False,
               f"dodges {P['dodges0']}->{dodges}, hp unchanged at "
               f"{player.hp:.0f}, live bullets={len(session.bullets.bullets)}")
        inp.bullet_time = True
        set_phase("fps_normal")
    return inp


def _strafe_input(elapsed_in_phase):
    direction = 1.0 if (elapsed_in_phase % 1.4) < 0.7 else -1.0
    yaw, _ = yaw_pitch_to(player.position, g3.position)
    return PlayerInput(move=Vec3(direction, 0, 0), aim_yaw=yaw)


def ph_fps_normal():
    if "f0" not in P:
        P.update(f0=frames, t0=_time.perf_counter(), scales=set())
    P["scales"].add(round(session.world_time_scale, 2))
    inp = _strafe_input(phase_elapsed())
    if phase_elapsed() >= 3.0:
        fps_n = (frames - P["f0"]) / (_time.perf_counter() - P["t0"])
        expect("fps_window_normal_scale_1", P["scales"] == {1.0},
               f"scales={P['scales']}")
        print(f"PROOF gate1 fps_normal={fps_n:.1f}", flush=True)
        hp0 = player.hp
        dodges0 = len([e for e in stunt.events
                       if e.action_type == "bullet_dodge"])
        set_phase("fps_bullet_time")
        P.update(f0=frames, t0=_time.perf_counter(), scales=set(),
                 fps_normal=fps_n, press_bt=True, hp0=hp0, dodges0=dodges0)
    return inp


def ph_fps_bullet_time():
    inp = _strafe_input(phase_elapsed())
    if "activated" not in P:
        # Bullet Time may be on its GDD 5s cooldown (the dodge phase
        # switched it off): keep pressing until it REALLY activates —
        # presses during cooldown are refused by the controller — and
        # only then start the measurement window.
        if player.bt_active:
            P["activated"] = True
            P["f0"] = frames
            P["t0"] = _time.perf_counter()
            P["scales"] = set()
            P["charge0"] = player.charge
        else:
            inp.bullet_time = True
            if timed_out(9):
                expect("bullet_time_scale_0.3", False,
                       "Bullet Time never activated (cooldown never lapsed?)")
                expect("bullet_time_charge_drains", False,
                       "no activation, no drain")
                set_phase("bt_off_check")
        return inp
    P["scales"].add(round(session.world_time_scale, 2))
    if _time.perf_counter() - P["t0"] >= 3.0:
        fps_bt = (frames - P["f0"]) / (_time.perf_counter() - P["t0"])
        fps_n = P["fps_normal"]
        diff = (fps_bt - fps_n) / fps_n * 100.0 if fps_n > 0 else 0.0
        print(f"PROOF gate1 fps_bullet_time={fps_bt:.1f} "
              f"fps_normal={fps_n:.1f} diff={diff:+.1f}%", flush=True)
        expect("gate1_fps_stable_in_bullet_time", fps_bt >= 0.65 * fps_n,
               f"fps_bt={fps_bt:.1f} vs fps_normal={fps_n:.1f} "
               f"({diff:+.1f}%) — severe-drop line at -35%")
        expect("bullet_time_scale_0.3", P["scales"] == {0.3},
               f"scales={P['scales']}")
        expect("bullet_time_charge_drains",
               player.charge < P["charge0"] - 12.0,
               f"charge {P['charge0']:.0f} -> {player.charge:.0f}")
        set_phase("bt_off_check")
    return inp


def ph_bt_off_check():
    inp = PlayerInput(move=Vec3(0, 0, 0))
    if player.bt_active and not P.get("pressed"):
        P["pressed"] = True
        inp.bullet_time = True
        return inp
    if not player.bt_active and phase_elapsed() > 0.4:
        expect("bullet_time_off_restores_scale",
               abs(session.world_time_scale - 1.0) < 1e-6,
               f"scale={session.world_time_scale}")
        set_phase("elevator")
    elif timed_out(6):
        expect("bullet_time_off_restores_scale", False,
               f"BT still active after 6s, scale={session.world_time_scale}")
        set_phase("elevator")
    return inp


def ph_elevator():
    inp, _ = goto_input(Vec3(0, 0, 13.2))
    if session.state == "won":
        verify_final_card()
        finish_all()
    elif session.state == "lost":
        expect("elevator_reached_win", False,
               f"stage lost: {session.final_record.get('reason')}")
        finish_all()
    elif timed_out(12):
        expect("elevator_reached_win", False, "timeout before the elevator")
        finish_all()
    return inp


# ---------------------------------------------------------------------------
# Gate 3 — the final report card, verified against the live state
# ---------------------------------------------------------------------------
def verify_final_card():
    rec = session.final_record
    result = session.result
    t_actual = session.timer.elapsed
    expected_s_time = int(max(0.0, (TARGET_TIME_S - t_actual)) * 100)
    expect("elevator_reached_win", True,
           f"elapsed={t_actual:.2f}s of {TARGET_TIME_S:.0f}s target")
    expect("gate3_s_time_matches_formula",
           rec["s_time"] == expected_s_time == result.s_time,
           f"recorded={rec['s_time']} expected={expected_s_time} "
           f"from T_actual={t_actual:.2f}s")
    expect("gate3_total_consistent",
           result.total == result.s_time
           + int(result.stunt_base * result.combo_multiplier),
           f"total={result.total} s_time={result.s_time} "
           f"stunt_base={result.stunt_base} combo={result.combo_multiplier}")
    rank, title = take_rating.rank_for_total(result.total)
    expect("gate3_rank_title_consistent",
           rec["rank"] == rank and rec["title"] == title,
           f"record={rec['rank']}/{rec['title']} table={rank}/{title}")
    expect("gate3_hud_dataset_complete",
           rec["hp"] == round(player.hp, 1)
           and rec["bullet_charge"] == round(player.charge, 1)
           and rec["stunt_score"] == stunt.current_score == hud._stunt_score
           and rec["combo"] == stunt.combo_multiplier
           and abs(rec["elapsed_s"] - t_actual) < 0.011
           and rec["target_s"] == TARGET_TIME_S
           and abs(hud._elapsed_s - t_actual) < 0.05,
           f"record={rec}")
    print("PROOF final report card (verbatim):", flush=True)
    print(session.final_card_text, flush=True)


PHASES = {
    "bullet_column_goto": ph_bullet_column_goto,
    "bullet_column_fire": ph_bullet_column_fire,
    "bullet_desk_goto": ph_bullet_desk_goto,
    "bullet_desk_fire": ph_bullet_desk_fire,
    "player_desk_push": ph_player_desk_push,
    "player_column_goto": ph_player_column_goto,
    "player_column_push": ph_player_column_push,
    "shoot_g1": ph_shoot_g1,
    "melee_g2": ph_melee_g2,
    "slide_goto": ph_slide_goto,
    "slide_run": ph_slide_run,
    "arena_goto": ph_arena_goto,
    "dodge": ph_dodge,
    "fps_normal": ph_fps_normal,
    "fps_bullet_time": ph_fps_bullet_time,
    "bt_off_check": ph_bt_off_check,
    "elevator": ph_elevator,
}

done = {"finished": False}


def finish_all():
    if done["finished"]:
        return
    done["finished"] = True
    elapsed = _time.perf_counter() - started
    fps = frames / elapsed if elapsed > 0 else 0.0
    print(f"PROOF run frames={frames} elapsed={elapsed:.2f}s "
          f"avg_fps={fps:.1f} (sandbox software rendering)", flush=True)
    verdict = "PASS" if not results["failures"] else "FAIL"
    print(f"PROOF level1_smoke {verdict}: {results['checks']} checks, "
          f"{len(results['failures'])} failures: {results['failures']}",
          flush=True)
    application.quit()


def update():
    global frames
    # Clamp dt to 1/30s: the sandbox renderer stalls during startup
    # (shader compilation), and one unclamped step (7.5u/s x ~0.5s)
    # exceeds the depth of furniture and tunnels the player through
    # it. Real games clamp dt for exactly this reason; FPS below is
    # still measured in rendered frames per real wall-clock second.
    dt = min(ursina_time.dt, 1.0 / 30.0)
    if dt <= 0 or done["finished"]:
        return
    frames += 1
    if _time.perf_counter() - started > GLOBAL_TIMEOUT_S:
        expect("global_timeout", False, f"phase={phase}")
        finish_all()
        return
    if session.state != "playing" and phase != "elevator":
        # The run is over (player down / time out / goal zone entered
        # early): stop exercising mechanics and let the elevator phase
        # record the outcome. A WIN here means the scripted route
        # crossed the goal zone before the final phase — a route
        # error, reported loudly, never silently absorbed.
        if session.state == "won":
            expect("no_premature_win", False,
                   f"goal zone entered during phase '{phase}'")
        set_phase("elevator")
    inp = PHASES[phase]()
    if not done["finished"]:
        session.tick(dt, inp)


app.run()
sys.exit(0 if not results["failures"] else 1)
