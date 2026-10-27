"""Integrated QA test for full_game_pipeline — ONE process, ONE run,
all three floors end-to-end (Cyrus's integration acceptance test).

Part 1 — pre-flight unit checks of the chain machinery (deterministic,
fake clocks): the heal-by-rank v1 table, RunState banking/rating math
on a synthetic floor, a failed floor stopping the chain, the Enforcer
adapter (frontal BLOCKED, flank kill scores SHIELD BYPASS exactly
once), the Marksman adapter (generic damage + the base death path),
and the Boss adapter passthrough.

Part 2 — the real run: a scripted autopilot plays the REAL pipeline
(FullGamePipeline with the real phase4 VictoryScreen injected) through
Lobby -> elevator -> Data Center -> elevator -> Penthouse + boss ->
final card, and asserts the chain rules against the run's own numbers:

  * the elevator transition scene rendered after floors 1 and 2, with
    the finished floor's real stats on the panel, frames advanced;
  * the StuntManager is ONE object across floors; its score/raw base
    at each floor's start equals the previous floor's end (never
    zeroed, never reset);
  * floor 2's timer cap == 75 + min(banked lobby seconds, 30), floor
    3's == 105 + min(banked Data Center seconds, 30) — the applied
    time-bank bonus is capped at +30 s (Cyrus's order, 2026-10-27);
    accrual itself stays uncapped and is asserted separately;
  * HP after each floor == the rank-table heal applied to the HP the
    floor ended with, and the next floor starts at exactly that HP;
  * the boss is defeated on floor 3;
  * the final card: S_total == SUM(floor S_time) + raw stunt base x
    final combo, recomputed independently via logic.take_rating;
    rank + title present; the real VictoryScreen is visible showing
    the pipeline's own result;
  * SaveBridge recorded one save_stage_result call per floor with the
    floor's number / S_total / actual time / rank (delivered= only
    when save_system.py is actually present — reported, never faked).

FPS per floor is reported (sandbox software rendering under Xvfb —
not a GPU prediction). Any failure is reported with its evidence; the
chain is never simulated.

Run:  xvfb-run -a /tmp/ursina-venv/bin/python test_full_pipeline.py
Exit code 0 = PASS, 1 = FAIL. PROOF lines go to stdout.
"""

import logging
import math
import os
import sys
import time as _time

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from ursina import Ursina, Vec3, application, destroy  # noqa: E402
from ursina import time as ursina_time  # noqa: E402

from logic import take_rating  # noqa: E402
from logic.stunt_manager import StuntManager  # noqa: E402
from logic.timer_manager import TimerManager  # noqa: E402
from pipeline_state import RunState, SaveBridge, heal_for_rank  # noqa: E402
from full_game_pipeline import (  # noqa: E402
    BossTargetAdapter, EnforcerTargetAdapter, FullGamePipeline,
    MarksmanTargetAdapter)
from phase4.game_ui_screens import VictoryScreen  # noqa: E402

app = Ursina(title="Action Star — Full Pipeline QA", vsync=False)

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
# Part 1 — pre-flight unit checks
# ===========================================================================
class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


# --- heal-by-rank v1 table -------------------------------------------------
for rank, hp, exp_hp, exp_heal in (
        ("S", 37.0, 100.0, 63.0), ("A", 30.0, 90.0, 60.0),
        ("A", 80.0, 100.0, 20.0), ("B", 30.0, 70.0, 40.0),
        ("C", 30.0, 55.0, 25.0), ("F", 30.0, 30.0, 0.0)):
    got_hp, got_heal = heal_for_rank(rank, hp)
    expect(f"unit_heal_{rank}_from_{hp:.0f}",
           abs(got_hp - exp_hp) < 1e-9 and abs(got_heal - exp_heal) < 1e-9,
           f"got hp={got_hp} heal={got_heal}, want {exp_hp}/{exp_heal}")

# --- RunState: banking + floor rating + heal on a synthetic floor ---------
rs = RunState()
clock = FakeClock()
timer = TimerManager(clock, rs.effective_target(90.0))
rs.attach_timer(timer)
timer.start()
clock.now = 30.0
rs.stunt.register("slide_shoot")     # raw 100, combo -> 1.5
timer.finish()
rec = rs.settle_floor(level_num=1, timer=timer, won=True,
                      reason="unit", hp_end_pre_heal=50.0,
                      stunt_base_start=0)
expect("unit_settle_floor_math",
       rec.s_time == 6000 and abs(rec.banked_out_s - 60.0) < 1e-9
       and rec.stunt_base_gained == 100 and rec.floor_s_total == 6150
       and rec.floor_rank == "B" and abs(rec.heal_applied - 40.0) < 1e-9
       and abs(rec.hp_after_heal - 90.0) < 1e-9
       and abs(rs.banked_seconds - 60.0) < 1e-9
       and abs(rs.effective_target(75.0) - 105.0) < 1e-9
       and abs(rec.banked_in_s) < 1e-9 and rec.effective_target_s == 90.0,
       f"s_time={rec.s_time} banked={rec.banked_out_s} total="
       f"{rec.floor_s_total} rank={rec.floor_rank} heal={rec.heal_applied} "
       f"(next cap 105 = 75 + min(60 banked, 30 cap): accrual uncapped, "
       f"application capped — Cyrus's +30 s order 2026-10-27)")

# --- applied time-bank bonus cap +30 s (Cyrus's order, 2026-10-27) --------
rs_cap = RunState()
rs_cap.banked_seconds = 84.3
expect("unit_bank_cap_84_3_applies_30",
       rs_cap.effective_target(75.0) == 105.0
       and rs_cap.effective_target(105.0) == 135.0,
       f"banked 84.3 -> targets {rs_cap.effective_target(75.0)}/"
       f"{rs_cap.effective_target(105.0)} (base + 30.0 exactly)")
rs_cap.banked_seconds = 12.0
expect("unit_bank_under_cap_applies_fully",
       rs_cap.effective_target(75.0) == 87.0,
       f"banked 12.0 -> target {rs_cap.effective_target(75.0)} (base + 12)")
# ...and through a real settle: 84.3 s remaining accrues in full (84.3
# in RunState.banked_seconds) while the next floor applies only +30.
rs_settle = RunState()
clock_cap = FakeClock()
timer_cap = TimerManager(clock_cap, rs_settle.effective_target(90.0))
rs_settle.attach_timer(timer_cap)
timer_cap.start()
clock_cap.now = 5.7          # 84.3 s remaining on the 90 s floor
timer_cap.finish()
rec_cap = rs_settle.settle_floor(level_num=1, timer=timer_cap, won=True,
                                 reason="unit cap", hp_end_pre_heal=100.0,
                                 stunt_base_start=0)
expect("unit_bank_settle_84_3_caps_application",
       abs(rec_cap.banked_out_s - 84.3) < 0.01
       and abs(rs_settle.banked_seconds - 84.3) < 0.01
       and rs_settle.effective_target(75.0) == 105.0,
       f"banked_out={rec_cap.banked_out_s} accrued="
       f"{rs_settle.banked_seconds:.2f} next_cap="
       f"{rs_settle.effective_target(75.0)}")

# --- a failed floor stops the chain ---------------------------------------
rs2 = RunState()
clock2 = FakeClock()
timer2 = TimerManager(clock2, 90.0)
rs2.attach_timer(timer2)
timer2.start()
clock2.now = 95.0
timer2.finish()
rec2 = rs2.settle_floor(level_num=1, timer=timer2, won=False,
                        reason="unit timeout", hp_end_pre_heal=50.0,
                        stunt_base_start=0)
expect("unit_failed_floor_stops_chain",
       rs2.chain_failed and rs2.failed_at_floor == 1
       and rec2.floor_rank == "F" and rec2.heal_applied == 0.0
       and abs(rs2.hp - 100.0) < 1e-9 and rs2.banked_seconds == 0.0,
       f"rank={rec2.floor_rank} hp_state={rs2.hp} banked={rs2.banked_seconds}")

# --- enemy target adapters --------------------------------------------------
from level1.lobby_level import CollisionWorld  # noqa: E402
from level1.player_controller_3d import PlayerInput  # noqa: E402
from stage3.enemy_archetypes import (  # noqa: E402
    BossEnemy, EnforcerEnemy, MarksmanEnemy)


class _HudStub:
    def __init__(self):
        self.notes = []

    def notify(self, points, label):
        self.notes.append((points, label))


class _PlayerStub:
    def __init__(self, pos):
        self.position = pos
        self.is_sliding = False


unit_world = CollisionWorld()
enf = EnforcerEnemy(unit_world, "ENF-UNIT", Vec3(0, 0.9, 0),
                    facing_yaw=180.0)      # faces -Z: front is -Z side
stub = _PlayerStub(Vec3(0, 0.9, -6))       # standing in front of him
stunt_u = StuntManager(FakeClock())
hud_u = _HudStub()
enf_adapter = EnforcerTargetAdapter(enf, stub, stunt_u, hud_u)
blocked = enf_adapter.take_shot_damage(50.0)
expect("unit_enforcer_frontal_blocked",
       blocked is False and enf.hp >= 850.0 and enf.blocked_shots == 1,
       f"hp={enf.hp:.0f} blocked_shots={enf.blocked_shots}")
stub.position = Vec3(0, 0.9, 6)            # behind him — the flank
died_at = None
for i in range(17):
    if enf_adapter.take_shot_damage(50.0):
        died_at = i + 1
        break
expect("unit_enforcer_flank_kill_shield_bypass_once",
       died_at == 17 and not enf.alive
       and [e.action_type for e in stunt_u.events] == ["shield_bypass"]
       and stunt_u.raw_base_total == 250,
       f"died_at_shot={died_at} events="
       f"{[e.action_type for e in stunt_u.events]} raw={stunt_u.raw_base_total}")

mrk = MarksmanEnemy(unit_world, "MRK-UNIT", Vec3(5, 0.9, 5))
mrk_adapter = MarksmanTargetAdapter(mrk)
marks = [mrk_adapter.take_shot_damage(34.0) for _ in range(5)]
expect("unit_marksman_adapter_damage_and_death",
       marks == [False, False, False, False, True]
       and not mrk.alive and mrk.state == "down",
       f"marks={marks} hp={mrk.hp:.0f} state={mrk.state}")

boss_u = BossEnemy(unit_world, "BOSS-UNIT", Vec3(0, 0.9, 20),
                   cover_points=[Vec3(0, 0, 20)])
boss_adapter = BossTargetAdapter(boss_u, stub)
hit = boss_adapter.take_shot_damage(34.0)
expect("unit_boss_adapter_passthrough",
       hit is False and abs(boss_u.hp - 1166.0) < 1e-9 and boss_u.alive,
       f"boss hp={boss_u.hp:.0f} (1200 - 34 through his own method)")
for ent in (enf.entity, mrk.entity, mrk.laser_entity, boss_u.entity):
    try:
        destroy(ent)
    except Exception:
        pass

# --- SaveBridge status (honest seam report, not a pass/fail) ---------------
bridge = SaveBridge()
print(f"PROOF save_system present={bridge.present} "
      f"import_error={bridge.import_error}", flush=True)

# ===========================================================================
# Part 2 — the real three-floor run
# ===========================================================================
victory_screen = VictoryScreen()
pipeline = FullGamePipeline(start_floor=1, victory_screen=victory_screen,
                            save_bridge=bridge)

started = _time.perf_counter()
GLOBAL_TIMEOUT_S = 560.0
frames = 0
done = {"finished": False}

# Per-floor segment accounting (FPS) + live observations.
segments = {}          # level_num -> {"t0","f0","cap","stunt_id","score0","raw0"}
transitions_seen = {}  # from_floor -> {"title","stats","frames"}
current = {"floor": None, "trans_t0": None, "trans_from": None}


def yaw_pitch_to(src, dst):
    d = dst - src
    yaw = math.degrees(math.atan2(d.x, d.z))
    pitch = math.degrees(math.atan2(d.y, math.hypot(d.x, d.z)))
    return yaw, pitch


A = {}   # autopilot scratch, reset per sub-phase
sub = {"name": None}


def set_sub(name):
    if sub["name"] != name:
        sub["name"] = name
        A.clear()
        print(f"PROOF autopilot -> {name}", flush=True)


def nav(points, timeout_s):
    """Waypoint following (level1 pattern) + a stuck detector: if the
    player barely moves for 1.5 s while steering (run-3 forensics: a
    head-on push into a partition face has no tangential slide, so the
    player would push forever), insert a perpendicular detour point —
    what a human player does without thinking. Returns (input, arrived).
    """
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


# ------------------------------------------------------------- floor 1
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
    # f1_to_elevator
    inp, arrived = nav([Vec3(8, 0, 6), Vec3(3, 0, 10.5), Vec3(0, 0, 13.2)],
                       20.0)
    return inp


# ------------------------------------------------------------- floor 2
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
            # Route bends NORTH of partition_b (x~12, z -11.5..-5.5):
            # the (13.5,-4) leg gives the movement a tangential slide
            # component along the partition face instead of a head-on
            # push (run-3 forensics).
            inp, arrived = nav([Vec3(9, 0, -10.5), Vec3(13.5, 0, -4),
                                Vec3(17.2, 0, -1)], 20.0)
            if not arrived:
                # Bullet Time covers the whole approach (run 1 lesson:
                # at normal speed the marksman's 30-dmg lock-on shots
                # killed the player in ~12 s). His lock builds on
                # WORLD time, so BT stretches it ~3x in real time —
                # and the Enforcer chasing from the west crawls too.
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


# ------------------------------------------------------------- floor 3
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
        # Bullet Time on the approach: the marksman's lock builds on
        # world time, so BT stretches his 1.5 s lock ~3x in real time.
        # (Applied to whichever input this tick produced, nav included;
        # presses while BT is active would toggle it OFF, so only
        # press when inactive — cooldown refusals are the controller's.)
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
    # f3_boss — orbit-standoff shooting (the level1 G1 pattern).
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


# ------------------------------------------------------------- bookkeeping
def observe():
    """Track floor segments / transitions as the pipeline moves."""
    if pipeline.phase == "floor" and pipeline.session is not None:
        num = pipeline.session.level_num
        if current["trans_from"] is not None:
            transitions_seen[current["trans_from"]]["frames"] = \
                pipeline.transition.frames
            current["trans_from"] = None
        if current["floor"] != num:
            current["floor"] = num
            sub["name"] = None
            A.clear()
            segments[num] = {
                "t0": _time.perf_counter(),
                "f0": pipeline.total_frames,
                "cap": pipeline.session.timer.time_cap,
                "banked_at_start": pipeline.run_state.banked_seconds,
                "stunt_id": id(pipeline.run_state.stunt),
                "score0": pipeline.run_state.stunt.current_score,
                "raw0": pipeline.run_state.stunt.raw_base_total,
                "hp0": pipeline.session.player.hp,
            }
            print(f"PROOF floor {num} started: cap="
                  f"{segments[num]['cap']:.1f}s banked_at_start="
                  f"{segments[num]['banked_at_start']:.2f}s stunt_score="
                  f"{segments[num]['score0']} raw={segments[num]['raw0']} "
                  f"hp={segments[num]['hp0']:.0f}", flush=True)
    elif pipeline.phase == "transition":
        rec = pipeline.transition.record
        if rec is not None and current["trans_from"] != rec.level_num:
            current["trans_from"] = rec.level_num
            transitions_seen[rec.level_num] = {
                "title": pipeline.transition.title_text_value,
                "stats": pipeline.transition.stats_text_value,
                "frames": None,
            }
            print(f"PROOF transition after floor {rec.level_num} shown:\n"
                  f"{pipeline.transition.title_text_value}\n"
                  f"{pipeline.transition.stats_text_value}", flush=True)
    else:
        if current["trans_from"] is not None:
            num = current["trans_from"]
            transitions_seen[num]["frames"] = pipeline.transition.frames
            current["trans_from"] = None


def floor_fps(num):
    seg = segments.get(num)
    if seg is None:
        return None
    end_t = seg.get("t1", _time.perf_counter())
    end_f = seg.get("f1", pipeline.total_frames)
    wall = end_t - seg["t0"]
    return (end_f - seg["f0"]) / wall if wall > 0 else 0.0


# ------------------------------------------------------------- assertions
def run_assertions():
    run = pipeline.run_state
    records = run.floor_records
    by_num = {r.level_num: r for r in records}

    expect("chain_reached_final_phase",
           pipeline.phase in ("final", "failed")
           and pipeline.final_record is not None,
           f"phase={pipeline.phase}")
    expect("three_floors_settled", len(records) == 3,
           f"records={[(r.level_num, r.outcome, r.floor_rank) for r in records]}")
    if len(records) < 3:
        for name in ("transition_after_floor1", "transition_after_floor2",
                     "stunt_manager_single_instance",
                     "stunt_continuity", "floor2_target_banked",
                     "floor3_target_banked", "heal_floor1_exact",
                     "heal_floor2_exact", "boss_defeated",
                     "final_card_arithmetic", "victory_screen_shown",
                     "save_calls_per_floor"):
            expect(name, False, "chain stopped before this evidence existed")
        return

    r1, r2, r3 = by_num[1], by_num[2], by_num[3]

    # Elevator transitions rendered with the floors' real stats.
    for num, rec in ((1, r1), (2, r2)):
        seen = transitions_seen.get(num)
        ok = (seen is not None and (seen["frames"] or 0) > 30
              and rec.stage_name.upper() in seen["title"]
              and "ELEVATOR" in seen["title"]
              and f"RANK {rec.floor_rank}" in seen["stats"]
              and f"{rec.s_time:,}" in seen["stats"])
        expect(f"transition_after_floor{num}", ok,
               f"seen={None if seen is None else (seen['frames'], seen['title'])}")

    # ONE StuntManager; score/raw continuous across floors.
    ids = {segments[n]["stunt_id"] for n in (1, 2, 3) if n in segments}
    expect("stunt_manager_single_instance",
           len(ids) == 1 and ids == {id(run.stunt)},
           f"ids={ids}")
    expect("stunt_continuity",
           segments[2]["score0"] == r1.stunt_score_end
           and segments[3]["score0"] == r2.stunt_score_end
           and segments[2]["raw0"] == r1.stunt_base_end
           and segments[3]["raw0"] == r2.stunt_base_end
           and r1.stunt_base_end > 0,
           f"f1 end score={r1.stunt_score_end} raw={r1.stunt_base_end}; "
           f"f2 start score={segments[2]['score0']} raw={segments[2]['raw0']}; "
           f"f2 end raw={r2.stunt_base_end}; f3 start raw={segments[3]['raw0']}")

    # Time banking — the exact numbers, with the applied bonus capped
    # at +30 s (Cyrus's order, 2026-10-27): cap = base + min(banked, 30).
    expect("floor2_target_banked",
           abs(segments[2]["cap"] - (75.0 + min(r1.banked_out_s, 30.0))) < 0.01
           and abs(r2.effective_target_s
                   - (75.0 + min(r1.banked_out_s, 30.0))) < 0.01
           and abs(r2.banked_in_s - min(r1.banked_out_s, 30.0)) < 0.01,
           f"cap={segments[2]['cap']:.2f} = 75 + min({r1.banked_out_s:.2f}, 30)")
    expect("floor3_target_banked",
           abs(segments[3]["cap"] - (105.0 + min(r2.banked_out_s, 30.0))) < 0.01
           and abs(r3.effective_target_s
                   - (105.0 + min(r2.banked_out_s, 30.0))) < 0.01
           and abs(r3.banked_in_s - min(r2.banked_out_s, 30.0)) < 0.01,
           f"cap={segments[3]['cap']:.2f} = 105 + min({r2.banked_out_s:.2f}, 30)")

    # Heal by rank — exact table math, carried into the next floor.
    for num, rec, nxt in ((1, r1, r2), (2, r2, r3)):
        exp_hp, exp_heal = heal_for_rank(rec.floor_rank,
                                         rec.hp_end_pre_heal)
        expect(f"heal_floor{num}_exact",
               abs(rec.hp_after_heal - exp_hp) < 0.051
               and abs(rec.heal_applied - exp_heal) < 0.051
               and abs(nxt.hp_start - rec.hp_after_heal) < 0.051
               and abs(segments[num + 1]["hp0"] - rec.hp_after_heal) < 0.051,
               f"rank={rec.floor_rank} hp {rec.hp_end_pre_heal:.0f} "
               f"+{rec.heal_applied:.0f} -> {rec.hp_after_heal:.0f}; "
               f"next floor started at {segments[num + 1]['hp0']:.0f}")

    expect("boss_defeated", r3.boss_defeated is True and r3.outcome == "WIN",
           f"boss_defeated={r3.boss_defeated} outcome={r3.outcome} "
           f"reason={r3.reason}")

    # Final card arithmetic, recomputed independently.
    total_s_time = r1.s_time + r2.s_time + r3.s_time
    recomputed = take_rating.evaluate(total_s_time, run.stunt.raw_base_total,
                                      run.stunt.combo_multiplier)
    fr = pipeline.final_record
    expect("final_card_arithmetic",
           fr["s_total"] == recomputed.total
           and fr["s_time_total"] == total_s_time
           and fr["stunt_base"] == run.stunt.raw_base_total
           and fr["s_total"] == total_s_time
           + int(run.stunt.raw_base_total * run.stunt.combo_multiplier)
           and pipeline.final_result.total == fr["s_total"],
           f"S_total={fr['s_total']} = S_time {total_s_time} + "
           f"{run.stunt.raw_base_total} x {run.stunt.combo_multiplier:.1f}")
    rank, title = take_rating.rank_for_total(recomputed.total)
    expect("final_rank_title_present",
           fr["rank"] == rank and fr["title"] == title and bool(fr["rank"]),
           f"rank={fr['rank']} title={fr['title']}")

    expect("victory_screen_shown",
           victory_screen.visible
           and victory_screen.outcome == "victory"
           and victory_screen.rank_text.text == fr["rank"],
           f"visible={victory_screen.visible} outcome="
           f"{victory_screen.outcome} screen_rank="
           f"{victory_screen.rank_text.text} pipeline_rank={fr['rank']}")

    calls = bridge.calls
    ok = len(calls) == 3 and all(
        c["method"] == "save_stage_result" and c["level_num"] == rec.level_num
        and c["score"] == rec.floor_s_total and c["rank"] == rec.floor_rank
        and abs(c["time_taken"] - rec.t_actual_s) < 0.01
        and c["delivered"] == bridge.present
        for c, rec in zip(calls, records))
    expect("save_calls_per_floor", ok,
           f"present={bridge.present} calls={calls}")


def print_chain_log():
    run = pipeline.run_state
    print("\n================ CHAIN LOG ================", flush=True)
    for rec in run.floor_records:
        fps = floor_fps(rec.level_num)
        print(f"FLOOR {rec.level_num} {rec.stage_name}: {rec.outcome} "
              f"({rec.reason}) | time {rec.t_actual_s:.2f}s / "
              f"{rec.effective_target_s:.1f}s (base {rec.base_target_s:.0f} "
              f"+ banked {rec.banked_in_s:.1f}) | S_time {rec.s_time:,} | "
              f"stunt +{rec.stunt_base_gained:,} base (run "
              f"{rec.stunt_base_end:,}, combo x{rec.combo_end:.1f}) | "
              f"floor total {rec.floor_s_total:,} RANK {rec.floor_rank} "
              f"({rec.floor_title}) | HP {rec.hp_end_pre_heal:.0f} "
              f"+{rec.heal_applied:.0f} -> {rec.hp_after_heal:.0f} | "
              f"banked out {rec.banked_out_s:.1f}s | boss_defeated="
              f"{rec.boss_defeated} | save delivered="
              f"{(rec.save_call or {}).get('delivered')} | "
              f"fps {fps:.1f}" if fps is not None else
              f"FLOOR {rec.level_num} {rec.stage_name}: {rec.outcome}",
              flush=True)
    fr = pipeline.final_record
    if fr is not None:
        print(f"FINAL CARD: outcome {fr['outcome']} | S_time total "
              f"{fr['s_time_total']:,} | stunt base {fr['stunt_base']:,} "
              f"x combo {fr['combo']:.1f} = {fr['stunt_component']:,} | "
              f"S_total {fr['s_total']:,} | RANK {fr['rank']} — "
              f"{fr['title']} | save_system_present="
              f"{fr['save_system_present']}", flush=True)
    print("==========================================\n", flush=True)


def finish_all():
    if done["finished"]:
        return
    done["finished"] = True
    # Close the last floor segment for FPS accounting.
    num = current["floor"]
    if num in segments and "t1" not in segments[num]:
        segments[num]["t1"] = _time.perf_counter()
        segments[num]["f1"] = pipeline.total_frames
    run_assertions()
    print_chain_log()
    elapsed = _time.perf_counter() - started
    fps = frames / elapsed if elapsed > 0 else 0.0
    print(f"PROOF run frames={frames} elapsed={elapsed:.2f}s "
          f"avg_fps={fps:.1f} (sandbox software rendering)", flush=True)
    verdict = "PASS" if not results["failures"] else "FAIL"
    print(f"PROOF full_pipeline {verdict}: {results['checks']} checks, "
          f"{len(results['failures'])} failures: {results['failures']}",
          flush=True)
    sys.stdout.flush()
    # os._exit: application.quit() makes the process exit 0 regardless
    # of the verdict (observed in runs 1-2), so the QA exit code is
    # enforced directly here.
    os._exit(0 if not results["failures"] else 1)


def update():
    global frames
    dt = min(ursina_time.dt, 1.0 / 30.0)
    if dt <= 0 or done["finished"]:
        return
    frames += 1
    if _time.perf_counter() - started > GLOBAL_TIMEOUT_S:
        expect("global_timeout", False,
               f"phase={pipeline.phase} floor={current['floor']} "
               f"sub={sub['name']}")
        finish_all()
        return
    observe()
    if pipeline.phase in ("final", "failed"):
        finish_all()
        return
    inp = PlayerInput()
    if pipeline.phase == "floor" and pipeline.session is not None:
        inp = AUTOPILOTS[pipeline.session.level_num]()
        if frames % 60 == 0 and pipeline.session.level_num >= 2:
            s = pipeline.session
            extra = ""
            if s.marksman is not None:
                extra += (f" mrk_lock={s.marksman.lock_progress:.2f} "
                          f"mrk_hp={s.marksman.hp:.0f}")
            if s.enforcer is not None:
                ep = s.enforcer.position
                extra += (f" enf=({ep.x:.0f},{ep.z:.0f}) "
                          f"enf_hp={s.enforcer.hp:.0f}")
            if s.boss is not None:
                extra += f" boss_hp={s.boss.hp:.0f}"
            p = s.player
            print(f"PROOF trace f{s.level_num} t={s.timer.elapsed:.1f} "
                  f"hp={p.hp:.0f} pos=({p.position.x:.1f},"
                  f"{p.position.z:.1f}) bt={p.bt_active} "
                  f"charge={p.charge:.0f} sub={sub['name']}{extra}",
                  flush=True)
    pipeline.tick(dt, inp)
    # Close a floor segment the moment its session settles.
    if pipeline.phase != "floor" and current["floor"] in segments \
            and "t1" not in segments[current["floor"]]:
        segments[current["floor"]]["t1"] = _time.perf_counter()
        segments[current["floor"]]["f1"] = pipeline.total_frames


app.run()
sys.exit(0 if not results["failures"] else 1)
