"""PlayerController3D — third-person character controller (Level 1).

WASD + mouse third-person action character for Action Star: NYC Siege 3D:

  * movement through the shared CollisionWorld (circle vs AABB);
  * shooting: hitscan with a visible tracer, 12-round magazine, timed
    reload, cover blocking (the lobby's collision ray decides whether a
    shot lands on a guard, on cover, or flies to max range);
  * melee: range- and arc-checked strike; a melee kill registers the
    Air Takedown stunt (the GDD's melee-takedown row);
  * slide: a timed, cooldown-gated slide; a shot that kills DURING the
    slide registers Slide & Shoot;
  * wall-running: running alongside a wall within reach attaches a
    wall-run (gravity suspended, body banked toward the wall, stuck
    at a fixed distance, up to 1.8 s); Space during the run is a
    wall jump (up + away + forward, ballistic landing); a kill
    DURING the wall-run registers the Wall-Run Kill stunt (+200);
  * the body is the code-built ActionStarModel (character_model.py) —
    poses (IDLE/RUN/AIM/SLIDE/MELEE/WALLRUN/DODGE) are driven from the
    controller's real state every tick;
  * shooting resolves from the CAMERA aim when a camera rig is wired
    (``camera_rig``): the crosshair line decides the aim point and the
    shot flies muzzle -> crosshair point, so cover checks stay honest
    from both ends. Without a rig it falls back to the character aim;
  * Bullet Time on L-SHIFT with the exact GDD physics (section 8): world
    time-scale 0.3x, energy drain 10%/s while active, recharge 5%/s
    while inactive, 5 s cooldown after deactivation, and the player
    exempt — the controller always ticks on REAL dt; the 0.3x factor is
    exposed as ``time_scale`` for the session to apply to guards and
    projectiles.

Wiring: stunt events go straight into the project's StuntManager, and
their floating notifications straight into the HUDManager (the session
pushes the per-frame HUD state). The controller knows guards only via
the ``targets`` list the session assigns — each target exposes
``alive``, ``position``, ``take_shot_damage(dmg) -> died`` and
``take_melee_damage(dmg) -> died``.

Input arrives as a :class:`PlayerInput` snapshot per tick, built by
main.py from the real keyboard/mouse for a human, or scripted by the QA
autopilot — both drive the identical code path.
"""

from __future__ import annotations

import logging
import math
import os
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ursina import Entity, Vec3, color, destroy  # noqa: E402

from character_model import ActionStarModel  # noqa: E402
from level1.lobby_level import CollisionWorld, forward_from_yaw  # noqa: E402
from logic.stunt_manager import STUNT_MATRIX  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
MOVE_SPEED = 7.5              # units per real second
PLAYER_RADIUS = 0.45
PLAYER_MAX_HP = 100.0
SPAWN_Y = 0.9                 # entity origin height (body centre)

# Bullet Time — GDD section 8, exact values.
BULLET_TIME_FACTOR = 0.3
BULLET_TIME_DRAIN_PER_S = 10.0
BULLET_TIME_RECHARGE_PER_S = 5.0
BULLET_TIME_COOLDOWN_S = 5.0

# Weapon
MAGAZINE_SIZE = 12
FIRE_INTERVAL_S = 0.16
RELOAD_TIME_S = 1.1
SHOT_DAMAGE = 34
SHOT_MAX_RANGE = 70.0
# Crosshair snap radius for the camera-aim cast: a target whose BODY
# SEGMENT passes within this distance of the camera's aim ray counts
# as "under the crosshair"; the aim point is the body point nearest
# the crosshair line (the part the crosshair actually rests on). This
# is the GDD section 6 AIM ASSIST, sized to cover the OTS shoulder
# parallax (1.15) — the bullet's own path is then still cover-checked
# from the muzzle at the tighter 0.95 centre test below, so a target
# the camera sees over low cover can still be unreachable from the
# muzzle (the shot stops on the cover, exactly as it should).
CROSSHAIR_SNAP_RADIUS = 1.3

# Melee
MELEE_DAMAGE = 55
MELEE_RANGE = 2.3
MELEE_ARC_COS = 0.2           # target must be roughly in front
MELEE_INTERVAL_S = 0.55

# Slide
SLIDE_DURATION_S = 0.65
SLIDE_COOLDOWN_S = 1.2        # after the slide ends
SLIDE_SPEED_START = 1.7       # x MOVE_SPEED at slide start, decaying to 1.0

# Wall-run (mechanics ported from Cyrus's Unity reference, 2026-10-27;
# scoring NOT ported — see CHARACTER-REPORT.md: points are kill-only)
WALL_REACH = 1.15             # centre-to-wall distance that can attach
WALLRUN_MAX_S = 1.8           # hard cap on one wall-run (Cyrus's tuning)
WALLRUN_Y = 1.5               # body-centre height held while attached
WALLRUN_REATTACH_LOCKOUT_S = 0.35
WALLRUN_PARALLEL_COS = 0.55   # travel must be this parallel to the wall
WALL_STICK_DIST = 0.8         # centre-to-wall distance held while stuck
WALLJUMP_UP_SPEED = 6.8       # vertical impulse of the wall jump
WALLJUMP_AWAY_SPEED = 4.5     # away-from-wall impulse of the wall jump
GRAVITY = 22.0                # units/s^2 while airborne


@dataclass
class PlayerInput:
    """One tick of input. ``move`` is a world-space direction (any
    magnitude; normalised internally, zero = stand still). ``aim_yaw`` /
    ``aim_pitch`` are absolute facing angles in degrees (None = keep).
    ``slide`` / ``melee`` / ``bullet_time`` / ``reload`` are press edges:
    True only on the tick the press happened (shooting is held-state)."""

    move: Vec3 = Vec3(0, 0, 0)
    aim_yaw: Optional[float] = None
    aim_pitch: float = 0.0
    shoot: bool = False
    melee: bool = False
    slide: bool = False
    bullet_time: bool = False
    reload: bool = False
    jump: bool = False        # press edge (Space); wall-jump while running


class PlayerController:
    """The action star. Construct after the Ursina app exists."""

    def __init__(self, world: CollisionWorld, stunt, hud,
                 spawn: Vec3 = Vec3(0, SPAWN_Y, -12.5)) -> None:
        self.world = world
        self.stunt = stunt
        self.hud = hud

        # The body IS the character model: its root is the controller's
        # entity (position/rotation semantics unchanged — the collision
        # gates measure exactly this root), the model owns the visuals
        # and poses below it.
        self.model = ActionStarModel(spawn=spawn)
        self.entity = self.model.root

        self.hp: float = PLAYER_MAX_HP
        self.max_hp: float = PLAYER_MAX_HP
        self.dead: bool = False
        self.radius: float = PLAYER_RADIUS
        self.aim_yaw: float = 0.0
        self.aim_pitch: float = 0.0

        # Session-assigned collaborators.
        self.targets: List = []
        self.on_shoot: Optional[Callable[[], None]] = None
        # The session's OTS camera rig (ThirdPersonCamera). When set,
        # shots resolve from the camera's crosshair aim; when None
        # (unit rigs), from the character's own aim angles.
        self.camera_rig = None

        # Bullet Time state.
        self.charge: float = 100.0
        self.bt_active: bool = False
        self._bt_cooldown_until: float = -1.0

        # Weapon state.
        self.ammo: int = MAGAZINE_SIZE
        self._fire_ready_at: float = 0.0
        self._reload_done_at: Optional[float] = None
        self.shots_fired: int = 0
        self.tracers_spawned: int = 0
        self.last_shot: dict = {"kind": "none", "distance": 0.0,
                                "solid": None, "target": None}
        self._tracers: List[dict] = []

        # Melee / slide state.
        self._melee_ready_at: float = 0.0
        self._melee_pose_until: float = -1.0
        self._slide_until: float = -1.0
        self._slide_ready_at: float = 0.0
        self._slide_dir: Vec3 = Vec3(0, 0, 1)

        # Wall-run state.
        self.wall_running: bool = False
        self._wallrun_side: int = 0       # +1 wall right of travel, -1 left
        self._wall_normal: Vec3 = Vec3(0, 0, 0)   # unit, wall -> player
        self._wallrun_until: float = -1.0
        self._wallrun_ready_at: float = 0.0

        # Airborne state (wall jump): simple ballistic verticals.
        self.airborne: bool = False
        self._vy: float = 0.0
        self._air_drift: Vec3 = Vec3(0, 0, 0)

        self._now: float = 0.0    # controller-local real-time clock (s)

    # ------------------------------------------------------------ properties
    @property
    def position(self) -> Vec3:
        return self.entity.position

    @property
    def time_scale(self) -> float:
        """World time-scale the session applies to guards/projectiles."""
        return BULLET_TIME_FACTOR if self.bt_active else 1.0

    @property
    def is_sliding(self) -> bool:
        return self._now < self._slide_until

    @property
    def is_wall_running(self) -> bool:
        return self.wall_running

    @property
    def is_reloading(self) -> bool:
        return self._reload_done_at is not None

    # ---------------------------------------------------------------- combat
    def take_damage(self, amount: float) -> None:
        """A guard bullet landed. Taking a hit resets the combo (GDD /
        StuntManager rule); banked score is never taken away."""
        if self.dead or amount <= 0:
            return
        self.hp = max(0.0, self.hp - float(amount))
        self.stunt.reset_combo()
        logger.info("Player hit for %.0f -> HP %.0f", amount, self.hp)
        if self.hp <= 0.0:
            self.dead = True
            logger.info("Player down")

    # ------------------------------------------------------------------ tick
    def tick(self, dt: float, inp: PlayerInput) -> None:
        if dt <= 0 or self.dead:
            return
        self._now += dt
        if inp.aim_yaw is not None:
            self.aim_yaw = float(inp.aim_yaw)
            self.aim_pitch = max(-40.0, min(40.0, float(inp.aim_pitch)))
        self.entity.rotation_y = self.aim_yaw

        self._tick_bullet_time(dt, inp)
        move_dir = self._tick_slide(dt, inp)
        move_dir = self._tick_wall_run(dt, inp, move_dir)
        self._tick_vertical(dt)
        self._tick_movement(dt, inp, move_dir)
        self._tick_weapon(dt, inp)
        self._tick_melee(inp)
        self._tick_tracers(dt)
        self._apply_pose(dt, inp, move_dir)

    # ------------------------------------------------------------- bullet time
    def _tick_bullet_time(self, dt: float, inp: PlayerInput) -> None:
        if inp.bullet_time:
            if self.bt_active:
                self._deactivate_bullet_time()
            elif self.charge > 1.0 and self._now >= self._bt_cooldown_until:
                self.bt_active = True
                logger.info("Bullet Time ON (charge %.0f%%)", self.charge)
        if self.bt_active:
            self.charge -= BULLET_TIME_DRAIN_PER_S * dt
            if self.charge <= 0.0:
                self.charge = 0.0
                self._deactivate_bullet_time()
        else:
            self.charge = min(100.0, self.charge
                              + BULLET_TIME_RECHARGE_PER_S * dt)

    def _deactivate_bullet_time(self) -> None:
        self.bt_active = False
        self._bt_cooldown_until = self._now + BULLET_TIME_COOLDOWN_S
        logger.info("Bullet Time OFF (cooldown %.0fs)", BULLET_TIME_COOLDOWN_S)

    # ------------------------------------------------------------------ slide
    def _tick_slide(self, dt: float, inp: PlayerInput) -> Vec3:
        """Returns the effective move direction for this tick (the locked
        slide direction while sliding, else the input direction)."""
        move = Vec3(float(inp.move.x), 0.0, float(inp.move.z))
        if move.length() > 1.0:
            move = move.normalized()
        if (inp.slide and not self.is_sliding
                and self._now >= self._slide_ready_at and move.length() > 0.1):
            self._slide_dir = move.normalized()
            self._slide_until = self._now + SLIDE_DURATION_S
            self._slide_ready_at = (self._slide_until + SLIDE_COOLDOWN_S)
            logger.info("Slide started")
        if self.is_sliding:
            # The slide's low profile is a MODEL pose now (SLIDE in
            # _apply_pose) — the root's scale is never touched, so the
            # collision footprint stays exactly the standing one.
            return self._slide_dir
        return move

    # -------------------------------------------------------------- wall-run
    def _tick_wall_run(self, dt: float, inp: PlayerInput,
                       move_dir: Vec3) -> Vec3:
        """Attach / sustain / detach the wall-run; returns the effective
        move direction (the wall tangent while attached).

        Attach: moving (not sliding, not airborne) with a wall within
        WALL_REACH on a lateral side and travel mostly parallel to it.
        Sustain: the wall must still be there on the same side (probed
        along the stored normal), input must not push away from the
        wall, the 1.8 s cap must not lapse. While attached, gravity is
        suspended: the body centre rises to WALLRUN_Y and HOLDS there,
        and the stick holds the centre at WALL_STICK_DIST from the
        wall face. Space during the run is the WALL JUMP: impulse up +
        away + forward, the run ends, ballistics take over (see
        _tick_vertical). On a plain detach the body eases back to the
        floor height (SPAWN_Y)."""
        pos = self.entity.position
        moving = move_dir.length() > 0.5 and not self.is_sliding

        if self.wall_running:
            if inp.jump:
                self._wall_jump(move_dir)
                return move_dir
            detach = None
            wall_hit = self.world.ray_hit_solid(
                pos + Vec3(0, 0.5, 0), -self._wall_normal,
                WALL_REACH + 0.3)
            if self.is_sliding:
                detach = "slide"
            elif self._now >= self._wallrun_until:
                detach = "time cap"
            elif move_dir.length() < 0.1:
                detach = "input stopped"
            elif move_dir.normalized().dot(self._wall_normal) > 0.45:
                detach = "turned away"
            elif wall_hit is None:
                detach = "wall ended"
            if detach is not None:
                self._end_wall_run(detach)
            else:
                # STICK: hold the centre at WALL_STICK_DIST from the
                # wall face — correct any drift in or out, gently.
                err = wall_hit[0] - WALL_STICK_DIST
                if abs(err) > 0.04:
                    step = max(-0.1, min(0.1, err))
                    self.entity.position = self.world.move(
                        self.entity.position, self.radius,
                        -self._wall_normal * step)
                # Run ALONG the wall: project travel onto the tangent.
                tangent = Vec3(-self._wall_normal.z, 0.0,
                               self._wall_normal.x)
                if tangent.dot(move_dir) < 0:
                    tangent = -tangent
                self._hold_wall_height(dt, WALLRUN_Y)
                return tangent * min(1.0, move_dir.length())
        elif moving and not self.airborne \
                and self._now >= self._wallrun_ready_at:
            right = Vec3(move_dir.z, 0.0, -move_dir.x)
            origin = pos + Vec3(0, 0.5, 0)
            for side in (1, -1):
                probe = right * side
                hit = self.world.ray_hit_solid(origin, probe, WALL_REACH)
                if hit is None:
                    continue
                if abs(move_dir.normalized().dot(probe)) \
                        > WALLRUN_PARALLEL_COS:
                    continue    # running INTO the wall, not alongside
                self.wall_running = True
                self._wallrun_side = side
                self._wall_normal = -probe
                self._wallrun_until = self._now + WALLRUN_MAX_S
                logger.info("Wall-run attached (side %+d, wall %s)",
                            side, hit[1])
                tangent = Vec3(-self._wall_normal.z, 0.0,
                               self._wall_normal.x)
                if tangent.dot(move_dir) < 0:
                    tangent = -tangent
                self._hold_wall_height(dt, WALLRUN_Y)
                return tangent * min(1.0, move_dir.length())

        # Not attached: if a wall-run lifted the body, gravity resumes
        # — ease the centre back to the floor height. (Airborne flight
        # is ballistic instead; _tick_vertical owns the height then.)
        if not self.airborne and abs(pos.y - SPAWN_Y) > 0.005:
            self._hold_wall_height(dt, SPAWN_Y, rate=6.0)
        return move_dir

    def _wall_jump(self, move_dir: Vec3) -> None:
        """Space during a wall-run: impulse UP + AWAY from the wall +
        FORWARD along the run, and the wall-run ends (Cyrus's Unity
        reference mechanics). Scores NOTHING by itself — the approved
        matrix pays only for a kill during the run."""
        tangent = Vec3(-self._wall_normal.z, 0.0, self._wall_normal.x)
        if tangent.dot(move_dir) < 0:
            tangent = -tangent
        self._air_drift = (self._wall_normal * WALLJUMP_AWAY_SPEED
                           + tangent * MOVE_SPEED * 0.8)
        self._vy = WALLJUMP_UP_SPEED
        self.airborne = True
        self._end_wall_run("wall jump")
        logger.info("Wall jump: drift=%s vy=%.1f",
                    self._air_drift, self._vy)

    def _tick_vertical(self, dt: float) -> None:
        """Ballistic height while airborne (wall jump): gravity pulls
        the centre back to the floor height; the jump's horizontal
        drift is applied through the collision world. Landing clears
        the airborne state."""
        if not self.airborne:
            return
        pos = self.entity.position
        if self._air_drift.length() > 0.01:
            self.entity.position = self.world.move(
                pos, self.radius, self._air_drift * dt)
            pos = self.entity.position
        self._vy -= GRAVITY * dt
        new_y = pos.y + self._vy * dt
        if new_y <= SPAWN_Y and self._vy < 0:
            self.entity.position = Vec3(pos.x, SPAWN_Y, pos.z)
            self._vy = 0.0
            self._air_drift = Vec3(0, 0, 0)
            self.airborne = False
            logger.info("Landed from wall jump")
        else:
            self.entity.position = Vec3(pos.x, new_y, pos.z)

    def _hold_wall_height(self, dt: float, target_y: float,
                          rate: float = 10.0) -> None:
        pos = self.entity.position
        step = min(1.0, dt * rate)
        self.entity.position = Vec3(pos.x,
                                    pos.y + (target_y - pos.y) * step,
                                    pos.z)

    def _end_wall_run(self, reason: str) -> None:
        self.wall_running = False
        self._wallrun_ready_at = self._now + WALLRUN_REATTACH_LOCKOUT_S
        logger.info("Wall-run ended (%s)", reason)

    @property
    def wallrun_side_facing(self) -> int:
        """Wall side relative to the FACING (aim): +1 = wall on the
        facing-right. Drives the model's bank toward the wall."""
        fwd = forward_from_yaw(self.aim_yaw)
        right = Vec3(fwd.z, 0.0, -fwd.x)
        return 1 if self._wall_normal.dot(right) < 0 else -1

    # ----------------------------------------------------------------- poses
    def _apply_pose(self, dt: float, inp: PlayerInput,
                    move_dir: Vec3) -> None:
        """Drive the ActionStarModel from the controller's real state."""
        moving = move_dir.length() > 0.1
        if self.wall_running:
            pose = "WALLRUN"
            self.model.set_wallrun_side(self.wallrun_side_facing)
        elif self.is_sliding:
            pose = "SLIDE"
        elif self._now < self._melee_pose_until:
            pose = "MELEE"
        elif self.bt_active and moving:
            pose = "DODGE"
        elif inp.shoot:
            pose = "AIM"
        elif moving:
            pose = "RUN"
        else:
            pose = "IDLE"
        if pose != self.model.pose:
            self.model.set_pose(pose)
        self.model.set_aim_pitch(self.aim_pitch)
        speed = MOVE_SPEED * (1.05 if self.wall_running else 1.0)
        self.model.update(dt, speed if moving else 0.0)

    def _tick_movement(self, dt: float, inp: PlayerInput,
                       move_dir: Vec3) -> None:
        if move_dir.length() < 1e-6:
            return
        speed = MOVE_SPEED
        if self.wall_running:
            speed *= 1.05
        if self.is_sliding:
            remaining = max(0.0, self._slide_until - self._now)
            frac = remaining / SLIDE_DURATION_S
            speed *= 1.0 + (SLIDE_SPEED_START - 1.0) * frac
        delta = move_dir.normalized() * speed * dt
        self.entity.position = self.world.move(self.entity.position,
                                               self.radius, delta)

    # ----------------------------------------------------------------- weapon
    def _tick_weapon(self, dt: float, inp: PlayerInput) -> None:
        if self._reload_done_at is not None and self._now >= self._reload_done_at:
            self._reload_done_at = None
            self.ammo = MAGAZINE_SIZE
            logger.info("Reloaded (%d rounds)", self.ammo)
        if inp.reload and self._reload_done_at is None \
                and self.ammo < MAGAZINE_SIZE:
            self._reload_done_at = self._now + RELOAD_TIME_S
        if not inp.shoot or self._reload_done_at is not None:
            return
        if self._now < self._fire_ready_at:
            return
        if self.ammo <= 0:
            self._reload_done_at = self._now + RELOAD_TIME_S
            return
        self._fire_ready_at = self._now + FIRE_INTERVAL_S
        self.ammo -= 1
        self.shots_fired += 1
        self._fire_once()
        if self.ammo == 0:
            self._reload_done_at = self._now + RELOAD_TIME_S
        if self.on_shoot is not None:
            self.on_shoot()

    def _aim_point_from_camera(self):
        """The crosshair point when a camera rig is wired: cast the
        camera's aim ray — a target under the crosshair IS the aim
        point; otherwise the first solid the crosshair rests on (or
        max range). Returns None when no rig ray is available yet."""
        if self.camera_rig is None:
            return None
        ray = self.camera_rig.aim_ray()
        if ray is None:
            return None
        cam_origin, cam_dir = ray
        cover = self.world.ray_hit_solid(cam_origin, cam_dir,
                                         SHOT_MAX_RANGE)
        limit = cover[0] if cover is not None else SHOT_MAX_RANGE
        best = None
        best_t = None
        for target in self.targets:
            if not target.alive:
                continue
            base = target.position
            mid = base + Vec3(0, 0.15, 0)
            rel = mid - cam_origin
            t = rel.dot(cam_dir)
            if t <= 0.0 or t > limit:
                continue
            # Distance from the aim ray to the target's vertical body
            # segment (base-0.6 .. base+0.75): the aim point is the
            # body point nearest the crosshair line.
            ray_point = cam_origin + cam_dir * t
            aim = Vec3(base.x,
                       max(base.y - 0.6,
                           min(base.y + 0.75, ray_point.y)),
                       base.z)
            if (ray_point - aim).length() > CROSSHAIR_SNAP_RADIUS:
                continue
            if best_t is None or t < best_t:
                best_t, best = t, aim
        if best is not None:
            return best
        return cam_origin + cam_dir * limit

    def _fire_once(self) -> None:
        """One hitscan round: cover vs guard vs open air, plus a tracer.

        With a camera rig wired, the shot resolves from the CAMERA aim:
        the direction is muzzle -> crosshair point (see
        _aim_point_from_camera), and cover is then re-checked along the
        bullet's real path — a shot can still be stopped by cover the
        camera sees over but the muzzle cannot. Without a rig, the
        character's own aim angles are used (original behaviour)."""
        origin = self.entity.position + Vec3(0, 0.5, 0)
        aim_point = self._aim_point_from_camera()
        if aim_point is not None:
            direction = (aim_point - origin).normalized()
        else:
            yaw = math.radians(self.aim_yaw)
            pitch = math.radians(self.aim_pitch)
            direction = Vec3(math.sin(yaw) * math.cos(pitch),
                             math.sin(pitch),
                             math.cos(yaw) * math.cos(pitch)).normalized()

        cover = self.world.ray_hit_solid(origin, direction, SHOT_MAX_RANGE)
        cover_t = cover[0] if cover is not None else None

        best_target = None
        best_t: Optional[float] = None
        for target in self.targets:
            if not target.alive:
                continue
            centre = target.position + Vec3(0, 0.15, 0)
            rel = centre - origin
            t = rel.dot(direction)
            if t <= 0.0 or t > SHOT_MAX_RANGE:
                continue
            closest = origin + direction * t
            if (closest - centre).length() > 0.95:
                continue
            if cover_t is not None and t > cover_t:
                continue    # a solid stands between the muzzle and the guard
            if best_t is None or t < best_t:
                best_t = t
                best_target = target

        if best_target is not None:
            end_t = best_t
            died = best_target.take_shot_damage(SHOT_DAMAGE)
            self.last_shot = {"kind": "guard", "distance": float(end_t),
                              "solid": None,
                              "target": getattr(best_target, "name", "?")}
            logger.info("Shot hit %s at %.1fu (died=%s)",
                        self.last_shot["target"], end_t, died)
            if died and self.is_sliding:
                self.stunt.register("slide_shoot")
                self.hud.notify(STUNT_MATRIX["slide_shoot"], "SLIDE & SHOOT")
            elif died and self.wall_running:
                self.stunt.register("wall_run_kill")
                self.hud.notify(STUNT_MATRIX["wall_run_kill"],
                                "WALL-RUN KILL")
        elif cover is not None:
            end_t = cover_t
            self.last_shot = {"kind": "cover", "distance": float(end_t),
                              "solid": cover[1], "target": None}
            logger.info("Shot blocked by cover %s at %.1fu",
                        cover[1], end_t)
        else:
            end_t = SHOT_MAX_RANGE
            self.last_shot = {"kind": "none", "distance": float(end_t),
                              "solid": None, "target": None}

        muzzle = origin + direction * 0.6
        end = origin + direction * end_t
        self._spawn_tracer(muzzle, end)

    def _spawn_tracer(self, start: Vec3, end: Vec3) -> None:
        mid = (start + end) / 2
        length = (end - start).length()
        tracer = Entity(model="cube", scale=(0.035, 0.035, max(0.1, length)),
                        position=mid, color=color.rgb(255, 220, 120))
        tracer.look_at(end)
        self._tracers.append({"entity": tracer, "ttl": 0.06})
        self.tracers_spawned += 1

    def _tick_tracers(self, dt: float) -> None:
        alive = []
        for item in self._tracers:
            item["ttl"] -= dt
            if item["ttl"] <= 0:
                destroy(item["entity"])
            else:
                alive.append(item)
        self._tracers = alive

    # ------------------------------------------------------------------ melee
    def _tick_melee(self, inp: PlayerInput) -> None:
        if not inp.melee or self._now < self._melee_ready_at:
            return
        self._melee_ready_at = self._now + MELEE_INTERVAL_S
        self._melee_pose_until = self._now + 0.3   # strike pose (MELEE)
        fwd = forward_from_yaw(self.aim_yaw)
        best = None
        best_dist = MELEE_RANGE
        for target in self.targets:
            if not target.alive:
                continue
            rel = target.position - self.entity.position
            rel.y = 0.0
            dist = rel.length()
            if dist > MELEE_RANGE or dist < 1e-6:
                continue
            if rel.normalized().dot(fwd) < MELEE_ARC_COS:
                continue
            if dist < best_dist:
                best_dist = dist
                best = target
        if best is None:
            return
        died = best.take_melee_damage(MELEE_DAMAGE)
        logger.info("Melee hit %s at %.1fu (died=%s)",
                    getattr(best, "name", "?"), best_dist, died)
        if died and self.wall_running:
            # A kill performed while wall-running scores the Wall-Run
            # Kill row (exactly one stunt per kill, as everywhere).
            self.stunt.register("wall_run_kill")
            self.hud.notify(STUNT_MATRIX["wall_run_kill"],
                            "WALL-RUN KILL")
        elif died:
            # The GDD's melee-takedown row: Air Takedown points.
            self.stunt.register("air_takedown")
            self.hud.notify(STUNT_MATRIX["air_takedown"], "AIR TAKEDOWN")
