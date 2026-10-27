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

from level1.lobby_level import LIT, CollisionWorld, forward_from_yaw  # noqa: E402
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

# Melee
MELEE_DAMAGE = 55
MELEE_RANGE = 2.3
MELEE_ARC_COS = 0.2           # target must be roughly in front
MELEE_INTERVAL_S = 0.55

# Slide
SLIDE_DURATION_S = 0.65
SLIDE_COOLDOWN_S = 1.2        # after the slide ends
SLIDE_SPEED_START = 1.7       # x MOVE_SPEED at slide start, decaying to 1.0


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


class PlayerController:
    """The action star. Construct after the Ursina app exists."""

    def __init__(self, world: CollisionWorld, stunt, hud,
                 spawn: Vec3 = Vec3(0, SPAWN_Y, -12.5)) -> None:
        self.world = world
        self.stunt = stunt
        self.hud = hud

        self.entity = Entity(model="cube", scale=(0.9, 1.8, 0.9),
                             position=spawn, color=color.orange, shader=LIT)
        self._head = Entity(model="cube", scale=(0.55, 0.5, 0.55),
                            position=(0, 1.12, 0), parent=self.entity,
                            color=color.rgb(235, 195, 150), shader=LIT)
        self._nose = Entity(model="cube", scale=(0.2, 0.2, 0.35),
                            position=(0, 1.05, 0.55), parent=self.entity,
                            color=color.rgb(60, 60, 70), shader=LIT)

        self.hp: float = PLAYER_MAX_HP
        self.max_hp: float = PLAYER_MAX_HP
        self.dead: bool = False
        self.radius: float = PLAYER_RADIUS
        self.aim_yaw: float = 0.0
        self.aim_pitch: float = 0.0

        # Session-assigned collaborators.
        self.targets: List = []
        self.on_shoot: Optional[Callable[[], None]] = None

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
        self._slide_until: float = -1.0
        self._slide_ready_at: float = 0.0
        self._slide_dir: Vec3 = Vec3(0, 0, 1)

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
        self._tick_movement(dt, inp, move_dir)
        self._tick_weapon(dt, inp)
        self._tick_melee(inp)
        self._tick_tracers(dt)

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
            self.entity.scale_y = 1.15
            return self._slide_dir
        self.entity.scale_y = 1.8
        return move

    def _tick_movement(self, dt: float, inp: PlayerInput,
                       move_dir: Vec3) -> None:
        if move_dir.length() < 1e-6:
            return
        speed = MOVE_SPEED
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

    def _fire_once(self) -> None:
        """One hitscan round: cover vs guard vs open air, plus a tracer."""
        origin = self.entity.position + Vec3(0, 0.5, 0)
        yaw = math.radians(self.aim_yaw)
        pitch = math.radians(self.aim_pitch)
        direction = Vec3(math.sin(yaw) * math.cos(pitch), math.sin(pitch),
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
        if died:
            # The GDD's melee-takedown row: Air Takedown points.
            self.stunt.register("air_takedown")
            self.hud.notify(STUNT_MATRIX["air_takedown"], "AIR TAKEDOWN")
