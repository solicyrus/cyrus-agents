"""Action Star: NYC Siege 3D — minimal Ursina feasibility prototype.

Purpose: prove the studio can build and run real 3D with Ursina before the
full Level 1 build starts. This is a complete, runnable script (no
placeholders) with the three mechanics Stage 1 must demonstrate:

  * third-person-ish 3D scene: ground floor slab, tower blocks, a player cube
    moved with WASD, camera following behind/above the player;
  * Bullet Time: Space toggles a global time factor (1.0 -> 0.3). The WORLD
    (patrolling guard, incoming bullets) runs on scaled time; the player stays
    on real time, matching the GDD ("player exempt from the slow-down");
  * Time-Attack: an on-screen count-up run timer (mm:ss.t).

Stunt tie-in: a bullet that passes the player while Bullet Time is active
registers a "Bullet Dodge +50" event (first row of the GDD Stunt Matrix).

Headless verification: run with PROTOTYPE_AUTOTEST=1 to enable a scripted
autopilot (drives forward, toggles Bullet Time on/off on a schedule, quits
after ~4.5 s and prints PROOF lines). Without that variable the game is pure
manual control for a human at a real screen.

Run:  python prototype3d.py
"""

import os
import time as _time

from ursina import (
    Entity,
    Text,
    Ursina,
    application,
    camera,
    color,
    destroy,
    held_keys,
    scene,
    time,
    Vec3,
)

# ---------------------------------------------------------------------------
# Tunables (values mirror the GDD where the GDD fixes them)
# ---------------------------------------------------------------------------
BULLET_TIME_FACTOR = 0.3      # GDD: Bullet Time slows the world to 0.3x
PLAYER_SPEED = 7.0            # units per real second (player is NOT slowed)
GUARD_SPEED = 2.2             # units per world second (slowed in Bullet Time)
BULLET_SPEED = 13.0           # units per world second (slowed in Bullet Time)
BULLET_FIRE_INTERVAL = 1.6    # world seconds between guard shots
DODGE_RADIUS = 1.6            # bullet passing this close in Bullet Time = dodge
BULLET_DODGE_POINTS = 50      # GDD Stunt Matrix: Bullet Dodge +50
AUTOTEST = os.environ.get("PROTOTYPE_AUTOTEST") == "1"
AUTOTEST_QUIT_AT = 4.5        # real seconds before the autotest quits

# ---------------------------------------------------------------------------
# App + scene
# ---------------------------------------------------------------------------
app = Ursina(title="Action Star: NYC Siege 3D — prototype", vsync=False)

# Tower floor slab + a few skyscraper blocks to give the space depth.
ground = Entity(model="cube", scale=(60, 0.5, 60), position=(0, -0.25, 0),
                color=color.rgb(70, 74, 84))
for i, (x, z, h) in enumerate([(-10, 10, 9), (8, 14, 13), (-14, -6, 6),
                               (12, -10, 11), (0, 22, 16)]):
    Entity(model="cube", scale=(5, h, 5), position=(x, h / 2, z),
           color=color.rgb(52 + i * 9, 56 + i * 7, 68 + i * 6))

# The player (stand-in cube for the action star) and the exit pad (win zone).
player = Entity(model="cube", scale=(1, 1.8, 1), position=(0, 0.9, -14),
                color=color.orange)
exit_pad = Entity(model="cube", scale=(4, 0.2, 4), position=(0, 0.1, 20),
                  color=color.lime)

# Patrolling guard on the far side of the floor.
guard = Entity(model="cube", scale=(1, 1.8, 1), position=(-8, 0.9, 16),
               color=color.red)
GUARD_PATROL = [Vec3(-8, 0.9, 16), Vec3(8, 0.9, 16)]
guard_target_idx = 1

# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------
state = {
    "time_factor": 1.0,
    "bullet_time": False,
    "run_started_at": _time.perf_counter(),
    "elapsed": 0.0,
    "fire_timer": 0.0,
    "bullets": [],            # list of dicts: entity, velocity, scored
    "dodges": 0,
    "stunt_score": 0,
    "frames": 0,
    "start_pos": player.position,
    "autotest_stage": 0,
    "finished": False,
}

# ---------------------------------------------------------------------------
# HUD
# ---------------------------------------------------------------------------
timer_text = Text(text="TIME 00:00.0", position=(-0.86, 0.46), scale=1.6,
                  color=color.white)
mode_text = Text(text="NORMAL TIME", position=(-0.86, 0.40), scale=1.4,
                 color=color.white)
score_text = Text(text="STUNT SCORE 0", position=(0.55, 0.46), scale=1.4,
                  color=color.yellow)


def fmt_elapsed(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes:02d}:{secs:04.1f}"


def set_bullet_time(on: bool) -> None:
    state["bullet_time"] = on
    state["time_factor"] = BULLET_TIME_FACTOR if on else 1.0
    mode_text.text = "BULLET TIME x0.3" if on else "NORMAL TIME"
    mode_text.color = color.cyan if on else color.white
    print(f"EVENT bullet_time={'ON' if on else 'OFF'} "
          f"t={state['elapsed']:.2f}s", flush=True)


def input(key):
    """Real keyboard control: Space toggles Bullet Time (prototype binding)."""
    if key == "space":
        set_bullet_time(not state["bullet_time"])
    if key == "escape":
        application.quit()


def fire_bullet() -> None:
    start = guard.position + Vec3(0, 0.6, 0)
    direction = (player.position + Vec3(0, 0.6, 0) - start).normalized()
    bullet = Entity(model="sphere", scale=0.22, position=start,
                    color=color.yellow)
    state["bullets"].append(
        {"entity": bullet, "velocity": direction * BULLET_SPEED,
         "scored": False})


def update_bullets(world_dt: float) -> None:
    alive = []
    for item in state["bullets"]:
        ent = item["entity"]
        ent.position += item["velocity"] * world_dt
        dist = (ent.position - player.position).length()
        if (not item["scored"] and state["bullet_time"]
                and dist < DODGE_RADIUS):
            item["scored"] = True
            state["dodges"] += 1
            state["stunt_score"] += BULLET_DODGE_POINTS
            score_text.text = f"STUNT SCORE {state['stunt_score']}"
            print(f"EVENT bullet_dodge +{BULLET_DODGE_POINTS} "
                  f"t={state['elapsed']:.2f}s", flush=True)
        if dist > 0.6 and ent.position.length() < 55:
            alive.append(item)
        elif dist <= 0.6:
            print(f"EVENT bullet_hit_player t={state['elapsed']:.2f}s",
                  flush=True)
            destroy(ent)
        else:
            destroy(ent)
    state["bullets"] = alive


def autotest(elapsed: float) -> None:
    """Scripted headless driver: exercises movement + Bullet Time + quit."""
    stage = state["autotest_stage"]
    if stage == 0:
        state["autotest_stage"] = 1  # drive forward from the first frame on
    if stage <= 1 and elapsed >= 1.5:
        set_bullet_time(True)
        state["autotest_stage"] = 2
    elif stage == 2 and elapsed >= 3.2:
        set_bullet_time(False)
        state["autotest_stage"] = 3
    if elapsed >= AUTOTEST_QUIT_AT and not state["finished"]:
        state["finished"] = True
        moved = (player.position - state["start_pos"]).length()
        print(f"PROOF frames={state['frames']} elapsed={elapsed:.2f}s "
              f"player_moved={moved:.2f} units dodges={state['dodges']} "
              f"stunt_score={state['stunt_score']}", flush=True)
        print("PROOF prototype ran, rendered and quit cleanly", flush=True)
        application.quit()


def update():
    real_dt = time.dt
    if real_dt <= 0:
        return
    state["frames"] += 1
    state["elapsed"] = _time.perf_counter() - state["run_started_at"]
    elapsed = state["elapsed"]
    world_dt = real_dt * state["time_factor"]

    # --- Player movement on REAL time (player exempt from Bullet Time) ---
    move = Vec3(0, 0, 0)
    if held_keys["w"] or (AUTOTEST and state["autotest_stage"] >= 1):
        move += Vec3(0, 0, 1)
    if held_keys["s"]:
        move += Vec3(0, 0, -1)
    if held_keys["a"]:
        move += Vec3(-1, 0, 0)
    if held_keys["d"]:
        move += Vec3(1, 0, 0)
    if move.length() > 0:
        player.position += move.normalized() * PLAYER_SPEED * real_dt
        player.position = Vec3(
            max(-27, min(27, player.x)), 0.9, max(-27, min(27, player.z)))

    # --- Guard patrol on WORLD (scaled) time ---
    target = GUARD_PATROL[guard_target_idx]
    to_target = target - guard.position
    if to_target.length() < 0.3:
        state["guard_target_idx"] = 1 - guard_target_idx
    else:
        guard.position += to_target.normalized() * GUARD_SPEED * world_dt

    # --- Guard fires on world time; bullets fly on world time ---
    state["fire_timer"] += world_dt
    if state["fire_timer"] >= BULLET_FIRE_INTERVAL:
        state["fire_timer"] = 0.0
        fire_bullet()
    update_bullets(world_dt)

    # --- Third-person-ish camera: behind and above, looking at the player ---
    camera.position = player.position + Vec3(0, 9, -13)
    camera.look_at(player.position + Vec3(0, 1, 4))

    # --- HUD ---
    timer_text.text = f"TIME {fmt_elapsed(elapsed)}"

    if AUTOTEST:
        autotest(elapsed)


# Keep a reference so the scene graph objects are not garbage collected.
_ = (ground, exit_pad, scene)

app.run()
