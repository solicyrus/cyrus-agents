"""Headless QA smoke test for Stage 3 (Data Center + Penthouse/Boss).

Builds the REAL Stage-3 levels and enemy archetypes under a real GL
context (Xvfb) and runs Cyrus's acceptance checks:

  (a) a bullet ray at the Data Center's smoked-glass partition is
      BLOCKED by the glass (the guard behind it is out of the line);
  (b) shooting a server rack dead discharges it and STUNS the enemy
      standing beside it;
  (c) the Enforcer's shield BLOCKS frontal shots (registered, no HP
      loss) while a flank shot and a slide-under (low) shot damage him;
  (d) the Marksman's red laser entity exists, paints the target, and
      his lock-on FIRES a shot that lands;
  (e) a penthouse window pane BREAKS and a thrown enemy registers
      DEFENESTRATION (500 base) in the StuntManager, combo math intact;
  (f) the boss spawns, his hud_data() is readable, he transitions to
      phase 2 at the 66% line, throws a sight-blocking smoke grenade —
      and the dedicated HUD boss bar (stage3/boss_hud.py) is hidden
      before the fight, tracks his HP through scripted damage, and
      hides again when he dies;
  (g) FPS measured with the boss + 3 enemies active in the penthouse
      (sandbox software rendering — not a GPU prediction);
  (h) sustained gunfire trips the Data Center sprinklers (state +
      visibility factor + water film);
  (i) destructible cover: a wooden desk shatters and its solid leaves
      the collision world — the same ray then flies to the far wall.

Run:  xvfb-run -a /tmp/ursina-venv/bin/python stage3/test_stage3_smoke.py
Exit code 0 = PASS, 1 = FAIL. PROOF lines go to stdout.
"""

import math
import os
import sys
import time as _time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from ursina import Ursina, Vec3, application  # noqa: E402
from ursina import time as ursina_time  # noqa: E402

from level1.enemy_ai_3d import BulletManager, Guard  # noqa: E402
import random  # noqa: E402

from logic.stunt_manager import StuntManager  # noqa: E402
from logic import take_rating  # noqa: E402
from stage3.data_center_level import DataCenterLevel  # noqa: E402
from stage3.penthouse_level import PenthouseLevel  # noqa: E402
from stage3.enemy_archetypes import BossEnemy, EnforcerEnemy, MarksmanEnemy  # noqa: E402
from stage3.boss_hud import BAR_FULL_WIDTH, BossHealthBar  # noqa: E402

app = Ursina(title="Action Star — Stage 3 smoke", vsync=False)

results = {"failures": [], "checks": 0}


def check(name, ok, detail=""):
    results["checks"] += 1
    line = f"PROOF check {name}: {'OK' if ok else 'FAIL'} {detail}".rstrip()
    print(line, flush=True)
    if not ok:
        results["failures"].append(name)


def expect(name, ok, detail=""):
    check(name, bool(ok), detail)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class PlayerStub:
    """Minimal player stand-in: the interface the bullet manager and
    the archetypes consume (position / hp / dead / take_damage)."""

    def __init__(self, pos):
        self._pos = Vec3(pos.x, pos.y, pos.z)
        self.hp = 100000.0
        self.dead = False
        self.hits_taken = 0

    @property
    def position(self):
        return self._pos

    def set_position(self, pos):
        self._pos = Vec3(pos.x, pos.y, pos.z)

    def take_damage(self, amount):
        self.hp -= float(amount)
        self.hits_taken += 1


# ===========================================================================
# Build the two floors
# ===========================================================================
dc = DataCenterLevel()
ph = PenthouseLevel()
expect("levels_built", len(dc.world.solids) >= 26 and len(ph.panes) == 10,
       f"dc_solids={len(dc.world.solids)} ph_solids={len(ph.world.solids)} "
       f"panes={len(ph.panes)} targets: dc {dc.TARGET_TIME_S:.0f}s "
       f"ph {ph.TARGET_TIME_S:.0f}s")

# ===========================================================================
# (a) Smoked glass blocks the bullet ray
# ===========================================================================
origin = Vec3(-4.0, 1.4, 0.0)
hit = dc.world.ray_hit_solid(origin, Vec3(1, 0, 0), 60.0)
guard_behind_x = 10.0
expect("a_glass_ray_blocked",
       hit is not None and hit[1].startswith("smoked_glass_partition"),
       f"hit={hit}")
if hit:
    expect("a_glass_stops_before_guard", hit[0] < guard_behind_x - origin.x,
           f"glass at {hit[0]:.2f}u; the guard behind the glass stands "
           f"at {guard_behind_x - origin.x:.2f}u — the round never reaches him")

# ===========================================================================
# (b) Server rack discharge stuns the enemy beside it
# ===========================================================================
rack = next(r for r in dc.racks if r.name == "rack_-13_1")
enforcer_dc = EnforcerEnemy(dc.world, "ENF-DC", Vec3(-13, 0.9, -1.6))
dc.register_enemy(enforcer_dc)
res_b = rack.take_shot_damage(999.0)
expect("b_rack_discharged", res_b["shock_triggered"] and rack.discharged,
       f"result={res_b}")
expect("b_enemy_stunned", enforcer_dc.name in res_b["stunned"]
       and enforcer_dc.is_stunned,
       f"stunned={res_b['stunned']}")
pos_before = Vec3(enforcer_dc.position.x, 0, enforcer_dc.position.z)
enforcer_dc.tick(1.0, Vec3(0, 0.9, 0), True, None)
moved = (Vec3(enforcer_dc.position.x, 0, enforcer_dc.position.z)
         - pos_before).length()
expect("b_stunned_enemy_does_not_act", moved < 1e-6 and enforcer_dc.is_stunned,
       f"moved={moved:.3f}u while stunned")
enforcer_dc.tick(2.5, Vec3(0, 0.9, 0), True, None)
expect("b_stun_expires", not enforcer_dc.is_stunned,
       f"after 3.5s of ticks stun_until passed")

# ===========================================================================
# (h) Sprinklers trip under sustained gunfire
# ===========================================================================
for _ in range(6):
    dc.note_gunfire(Vec3(-5, 0, -5))
dc.tick(0.05)
expect("h_sprinklers_active", dc.sprinkler_active
       and dc.sprinkler_zone == (0, 0),
       f"active={dc.sprinkler_active} zone={dc.sprinkler_zone}")
expect("h_visibility_reduced", abs(dc.visibility_factor - 0.55) < 1e-9
       and dc._water_film.enabled
       and any(d.enabled for d in dc._droplets),
       f"visibility={dc.visibility_factor}")

# ===========================================================================
# (i) Destructible cover: the desk shatters, the ray flies through
# ===========================================================================
desk = next(c for c in dc.covers if c.name == "desk_wood_west")
ray_origin = Vec3(-2.0, 1.0, -10.0)
hit_before = dc.world.ray_hit_solid(ray_origin, Vec3(0, 0, 1), 60.0)
broke = desk.take_damage(70.0)
hit_after = dc.world.ray_hit_solid(ray_origin, Vec3(0, 0, 1), 60.0)
expect("i_desk_breaks", broke and desk.broken
       and "desk_wood_west" not in [s.name for s in dc.world.solids],
       f"broke={broke} hp={desk.hp}")
expect("i_ray_passes_after_break",
       hit_before is not None and hit_before[1] == "desk_wood_west"
       and hit_after is not None and hit_after[1] == "wall_north"
       and hit_after[0] > hit_before[0],
       f"before={hit_before} after={hit_after}")

# ===========================================================================
# (c) Enforcer shield: frontal blocked, flank + slide-under land
# ===========================================================================
enf = EnforcerEnemy(ph.world, "ENF-PH", Vec3(0, 0.9, 0), facing_yaw=180.0)
front = Vec3(0, 0.9, -6)     # he faces -Z (yaw 180): this is his front
behind = Vec3(0, 0.9, 6)
r1 = enf.take_shot_damage(50.0, front)
expect("c_frontal_shot_blocked", r1 == "blocked" and enf.hp >= 850.0
       and enf.blocked_shots == 1,
       f"result={r1} hp={enf.hp:.0f} blocked={enf.blocked_shots}")
r2 = enf.take_shot_damage(50.0, behind)
expect("c_flank_shot_damages", r2 == "hit" and abs(enf.hp - 800.0) < 1e-6,
       f"result={r2} hp={enf.hp:.0f}")
r3 = enf.take_shot_damage(50.0, front, low_attack=True)
expect("c_slide_under_damages", r3 == "hit" and abs(enf.hp - 750.0) < 1e-6,
       f"result={r3} hp={enf.hp:.0f} (slide-under bypasses the shield)")

# ===========================================================================
# (d) Marksman: laser exists, lock-on fires and lands
# ===========================================================================
stub_d = PlayerStub(Vec3(0, 0.9, -2))
marksman = MarksmanEnemy(ph.world, "MRK-PH", Vec3(18, 0.9, -12))
marksman.damage_sink = stub_d.take_damage
saw_laser = False
for _ in range(30):
    marksman.tick(0.1, stub_d.position, True, None)
    saw_laser = saw_laser or marksman.laser_active
expect("d_laser_entity_exists", marksman.laser_entity is not None,
       "laser entity constructed with the marksman")
expect("d_laser_paints_target", saw_laser,
       f"laser_active seen during lock-on: {saw_laser}")
expect("d_lock_on_fired_and_hit", marksman.shots_fired >= 1
       and marksman.last_shot_hit is True and stub_d.hits_taken == 1,
       f"shots={marksman.shots_fired} hit={marksman.last_shot_hit} "
       f"player_hits={stub_d.hits_taken}")

# ===========================================================================
# (e) Defenestration through a penthouse pane
# ===========================================================================
guard_e = Guard(ph.world, "G-PH", [Vec3(3.8, 0, -11), Vec3(4.2, 0, -11)],
                random.Random(3))
guard_e.entity.position = Vec3(3.83, 0.9, -13.0)
stunt_e = StuntManager(FakeClock())
pane_names_before = [s.name for s in ph.world.solids]
res_e = ph.throw_enemy_out(guard_e, stunt_e)
ev = stunt_e.events[-1] if stunt_e.events else None
expect("e_pane_broken", res_e["pane"] == "window_south_3"
       and res_e["pane"] in pane_names_before
       and res_e["pane"] not in [s.name for s in ph.world.solids],
       f"result={res_e}")
expect("e_defenestration_registered", ev is not None
       and ev.action_type == "defenestration" and ev.base_points == 500
       and res_e["stunt_points"] == 750,
       f"event={ev} (500 base x1.5 first-action combo = 750)")
rated = take_rating.evaluate(0, stunt_e.raw_base_total,
                             stunt_e.combo_multiplier)
expect("e_combo_math_intact", stunt_e.raw_base_total == 500
       and rated.total == 750 and rated.stunt_base == 500,
       f"raw_base={stunt_e.raw_base_total} rated_total={rated.total}")
expect("e_enemy_defeated_outside", (not guard_e.alive)
       and guard_e.state == "defenestrated"
       and guard_e.position.z < -19.0,
       f"alive={guard_e.alive} state={guard_e.state} "
       f"pos={guard_e.position}")

# ===========================================================================
# (f) Boss: spawn, phases, smoke — and the HUD boss bar tracking his HP
# ===========================================================================
boss = BossEnemy(ph.world, "BOSS", Vec3(0, 0.9, 10),
                 cover_points=[Vec3(-8, 0, 10), Vec3(8, 0, 10),
                               Vec3(0, 0, 13)],
                 rng=random.Random(5))
bar = BossHealthBar()
expect("f_bar_hidden_before_fight", not bar.visible,
       "no boss fight yet -> the bar is not on screen")
bar.begin_fight(boss)
data0 = boss.hud_data()
expect("f_boss_spawned_data_readable",
       data0["max_hp"] == 1200.0 and data0["phase"] == 1
       and abs(data0["fraction"] - 1.0) < 1e-9,
       f"hud_data={data0}")
expect("f_bar_shows_full_hp", bar.visible
       and abs(bar.displayed_fraction - 1.0) < 1e-6
       and abs(bar.fill_scale_x - BAR_FULL_WIDTH) < 1e-6
       and "1200" in bar.hp_text_value,
       f"fraction={bar.displayed_fraction} fill={bar.fill_scale_x:.3f} "
       f"text='{bar.hp_text_value}'")
boss.take_shot_damage(500.0)
bar.update()
frac = 700.0 / 1200.0
expect("f_bar_tracks_hp_after_damage", bar.visible
       and abs(bar.displayed_fraction - frac) < 0.01
       and abs(bar.fill_scale_x - BAR_FULL_WIDTH * frac) < 0.01
       and "700" in bar.hp_text_value
       and "PHASE 2" in str(bar._name_text.text),
       f"fraction={bar.displayed_fraction:.3f} (boss {frac:.3f}) "
       f"fill={bar.fill_scale_x:.3f} text='{bar.hp_text_value}' "
       f"name='{bar._name_text.text}'")
expect("f_phase_transition_at_66pct", boss.phase == 2
       and any(e[0] == "phase_change" and e[2] == 2 for e in boss.events),
       f"phase={boss.phase} events={boss.events}")
cloud = boss.throw_smoke_grenade(Vec3(0, 0, 0))
blocked = boss.sight_blocked(Vec3(-6, 1.3, 0), Vec3(6, 1.3, 0))
expect("f_smoke_grenade_blocks_sight", boss.grenades_thrown == 1
       and len(boss.smoke_clouds) == 1 and blocked,
       f"grenades={boss.grenades_thrown} sight_blocked={blocked}")
boss.take_shot_damage(700.0)
bar.update()
expect("f_bar_hides_when_boss_dies", not boss.alive and not bar.visible,
       f"boss alive={boss.alive} bar visible={bar.visible}")

# ===========================================================================
# (g) FPS — boss + 3 enemies live in the penthouse, real render loop
# ===========================================================================
stub_g = PlayerStub(Vec3(6, 0.9, 0))
stunt_g = StuntManager(FakeClock())
bullets_g = BulletManager(ph.world)
boss_g = BossEnemy(ph.world, "BOSS-G", Vec3(0, 0.9, 10),
                   cover_points=[Vec3(-8, 0, 10), Vec3(8, 0, 10),
                                 Vec3(0, 0, 13)],
                   rng=random.Random(11))
enf_g = EnforcerEnemy(ph.world, "ENF-G", Vec3(-8, 0.9, 6))
mrk_g = MarksmanEnemy(ph.world, "MRK-G", Vec3(18, 0.9, -12))
mrk_g.damage_sink = stub_g.take_damage
guard_g = Guard(ph.world, "G-G", [Vec3(-14, 0, 4), Vec3(-9, 0, 4)],
                random.Random(13))
bar_g = BossHealthBar()
bar_g.begin_fight(boss_g)

frames = 0
started = _time.perf_counter()
FPS_WINDOW_S = 4.0
angle = {"a": 0.0}
done = {"finished": False}


def finish_all():
    if done["finished"]:
        return
    done["finished"] = True
    elapsed = _time.perf_counter() - started
    fps = frames / elapsed if elapsed > 0 else 0.0
    print(f"PROOF gate_g frames={frames} elapsed={elapsed:.2f}s "
          f"fps={fps:.1f} (sandbox software rendering)", flush=True)
    expect("g_fps_measured_with_boss_and_3_enemies", frames > 30 and fps > 5.0,
           f"fps={fps:.1f} boss_shots={boss_g.shots_fired} "
           f"enforcer_shots={enf_g.shots_fired} "
           f"marksman_shots={mrk_g.shots_fired} "
           f"guard_shots={guard_g.shots_fired}")
    expect("g_boss_bar_live_during_fight", bar_g.visible,
           f"fraction={bar_g.displayed_fraction:.2f}")
    verdict = "PASS" if not results["failures"] else "FAIL"
    print(f"PROOF stage3_smoke {verdict}: {results['checks']} checks, "
          f"{len(results['failures'])} failures: {results['failures']}",
          flush=True)
    application.quit()
    sys.exit(0 if not results["failures"] else 1)


def update():
    global frames
    dt = ursina_time.dt
    if dt <= 0 or done["finished"]:
        return
    frames += 1
    angle["a"] += dt * 0.45
    stub_g.set_position(Vec3(math.cos(angle["a"]) * 6.0, 0.9,
                             math.sin(angle["a"]) * 6.0))
    boss_g.tick(dt, stub_g.position, True, bullets_g)
    enf_g.tick(dt, stub_g.position, True, bullets_g)
    mrk_g.tick(dt, stub_g.position, True, None)
    guard_g.tick(dt, stub_g.position, True, bullets_g)
    bullets_g.tick(dt, stub_g, stunt_g, False)
    bar_g.update()
    ph.tick(dt)
    if _time.perf_counter() - started >= FPS_WINDOW_S:
        finish_all()


app.run()
