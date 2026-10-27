"""EnemyAI3D — armed lobby guards + their projectiles (Level 1).

Guard state machine (per guard):

  PATROL .. walks its waypoint loop at patrol speed, scanning.
  ALERT ... a transitional beat: the guard has just perceived the player
            (sight, or a gunshot within earshot) and turns to engage;
            after ALERT_REACT_S it is fully ENGAGE. Kept as its own
            state so the perception event is observable in logs/tests.
  ENGAGE .. combat: keeps a fighting distance (approaches when far,
            strafes when in band, backs off when crowded), and fires real
            projectiles at the player whenever line of sight is clear.

Perception: sight needs range + a clear line of sight through the
shared CollisionWorld (guards cannot see through marble). Gunfire is
heard within GUNSHOT_HEAR_RADIUS and sends the guard to investigate /
engage the shooter's position.

Projectiles are real moving entities (world-time scaled, so Bullet Time
slows them): BulletManager flies them, checks wall impact against the
collision world, registers a player HIT (damage; the controller applies
the combo reset) or — when a bullet passes within DODGE_RADIUS of the
player while Bullet Time is active without hitting — a Bullet Dodge
stunt into the StuntManager, once per bullet.
"""

from __future__ import annotations

import logging
import math
import os
import random
import sys
from typing import Callable, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ursina import Entity, Vec3, color, destroy  # noqa: E402

from level1.lobby_level import LIT, CollisionWorld, yaw_towards  # noqa: E402
from logic.stunt_manager import STUNT_MATRIX  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
GUARD_MAX_HP = 100.0
GUARD_RADIUS = 0.45
PATROL_SPEED = 2.0
ENGAGE_SPEED = 3.4
SIGHT_RANGE = 27.0
GUNSHOT_HEAR_RADIUS = 28.0
ALERT_REACT_S = 0.35          # perception -> full engagement
FIRE_INTERVAL_S = 1.5         # world seconds between shots (+ jitter)
FIRE_RANGE = 30.0
ENGAGE_FAR = 14.0             # approach while farther than this
ENGAGE_NEAR = 8.0             # back off while closer than this
STRAFE_SPEED = 1.6
LOSE_SIGHT_S = 3.5            # unseen this long -> return to patrol

BULLET_SPEED = 16.0           # world units per world second
BULLET_DAMAGE = 7.0
BULLET_HIT_RADIUS = 0.8
DODGE_RADIUS = 1.7            # pass this close in Bullet Time = a dodge
BULLET_MAX_LIFE_S = 6.0


class Guard:
    """One armed lobby guard. Construct after the Ursina app exists."""

    def __init__(self, world: CollisionWorld, name: str,
                 patrol_points: List[Vec3], rng: random.Random) -> None:
        if len(patrol_points) < 2:
            raise ValueError("a guard needs at least 2 patrol points")
        self.world = world
        self.name = name
        self.rng = rng
        self.patrol_points = [Vec3(p.x, 0.9, p.z) for p in patrol_points]
        self._wp_index = 1

        start = self.patrol_points[0]
        self.entity = Entity(model="cube", scale=(0.9, 1.8, 0.9),
                             position=start, color=color.rgb(178, 44, 44),
                             shader=LIT)
        self._visor = Entity(model="cube", scale=(0.6, 0.18, 0.2),
                             position=(0, 1.15, 0.42), parent=self.entity,
                             color=color.rgb(30, 30, 36), shader=LIT)
        self._gun = Entity(model="cube", scale=(0.16, 0.16, 0.7),
                           position=(0.42, 0.35, 0.4), parent=self.entity,
                           color=color.rgb(24, 24, 28), shader=LIT)

        self.hp: float = GUARD_MAX_HP
        self.alive: bool = True
        self.state: str = "patrol"        # patrol | alert | engage
        self._alert_until: float = 0.0
        self._last_seen: Optional[Vec3] = None
        self._unseen_for: float = 0.0
        self._next_fire_at: float = rng.uniform(0.4, 1.2)
        self._strafe_dir: float = 1.0
        self._strafe_switch_at: float = 0.0
        self._now: float = 0.0            # guard-local world-time clock
        self.shots_fired: int = 0

    # ------------------------------------------------------------ properties
    @property
    def position(self) -> Vec3:
        return self.entity.position

    # --------------------------------------------------------- damage / death
    def take_shot_damage(self, dmg: float) -> bool:
        """Bullet damage. Returns True when this hit kills the guard."""
        return self._apply_damage(dmg, "shot")

    def take_melee_damage(self, dmg: float) -> bool:
        """Melee damage. Returns True when this hit kills the guard."""
        return self._apply_damage(dmg, "melee")

    def _apply_damage(self, dmg: float, source: str) -> bool:
        if not self.alive:
            return False
        self.hp = max(0.0, self.hp - float(dmg))
        logger.info("Guard %s took %.0f %s damage -> HP %.0f",
                    self.name, dmg, source, self.hp)
        if self.hp <= 0.0:
            self.alive = False
            self.state = "down"
            self.entity.rotation_z = 88
            self.entity.y = 0.45
            self.entity.color = color.rgb(90, 40, 40)
            logger.info("Guard %s is DOWN", self.name)
            return True
        # Getting shot instantly alerts the guard.
        self._become_alert(self._last_seen)
        return False

    # ------------------------------------------------------------- perception
    def hear_gunshot(self, shooter_pos: Vec3) -> None:
        """A shot fired within earshot: engage toward the shooter."""
        if not self.alive:
            return
        if (shooter_pos - self.entity.position).length() <= GUNSHOT_HEAR_RADIUS:
            self._last_seen = Vec3(shooter_pos.x, 0.9, shooter_pos.z)
            self._become_alert(self._last_seen)
            logger.info("Guard %s heard gunfire", self.name)

    def _become_alert(self, seen_pos: Optional[Vec3]) -> None:
        if self.state == "patrol":
            self.state = "alert"
            self._alert_until = self._now + ALERT_REACT_S
            if seen_pos is not None:
                self._last_seen = Vec3(seen_pos.x, 0.9, seen_pos.z)

    def _can_see(self, player_pos: Vec3) -> bool:
        eye = self.entity.position + Vec3(0, 0.55, 0)
        chest = player_pos + Vec3(0, 0.35, 0)
        if (chest - eye).length() > SIGHT_RANGE:
            return False
        return self.world.line_of_sight(eye, chest)

    # ------------------------------------------------------------------ tick
    def tick(self, dt: float, player_pos: Vec3, player_alive: bool,
             bullets: "BulletManager") -> None:
        """Advance the guard by ``dt`` WORLD seconds (Bullet-Time scaled)."""
        if dt <= 0 or not self.alive:
            return
        self._now += dt
        sees = player_alive and self._can_see(player_pos)
        if sees:
            self._last_seen = Vec3(player_pos.x, 0.9, player_pos.z)
            self._unseen_for = 0.0
            if self.state == "patrol":
                self._become_alert(player_pos)
        elif self.state in ("alert", "engage"):
            self._unseen_for += dt

        if self.state == "alert" and self._now >= self._alert_until:
            self.state = "engage"
            logger.info("Guard %s ENGAGED", self.name)

        if self.state == "patrol":
            self._tick_patrol(dt)
        elif self.state == "engage":
            self._tick_engage(dt, player_pos, bullets, sees)
            if self._unseen_for > LOSE_SIGHT_S:
                self.state = "patrol"
                self._unseen_for = 0.0
                logger.info("Guard %s lost the player, back to patrol",
                            self.name)

    def _face(self, target: Vec3) -> None:
        rel = target - self.entity.position
        if rel.length() > 1e-4:
            self.entity.rotation_y = yaw_towards(rel.x, rel.z)

    def _move_towards(self, target: Vec3, speed: float, dt: float) -> float:
        rel = target - self.entity.position
        rel.y = 0.0
        dist = rel.length()
        if dist < 1e-4:
            return 0.0
        step = rel.normalized() * min(speed * dt, dist)
        self.entity.position = self.world.move(self.entity.position,
                                               GUARD_RADIUS, step)
        self._face(target)
        return dist

    def _tick_patrol(self, dt: float) -> None:
        target = self.patrol_points[self._wp_index]
        dist = self._move_towards(target, PATROL_SPEED, dt)
        if dist < 0.4:
            self._wp_index = (self._wp_index + 1) % len(self.patrol_points)

    def _tick_engage(self, dt: float, player_pos: Vec3,
                     bullets: "BulletManager", sees: bool) -> None:
        target = self._last_seen if self._last_seen is not None else player_pos
        rel = target - self.entity.position
        rel.y = 0.0
        dist = rel.length()
        self._face(target)

        if dist > ENGAGE_FAR:
            self._move_towards(target, ENGAGE_SPEED, dt)
        elif dist < ENGAGE_NEAR:
            away = self.entity.position - target
            away.y = 0.0
            if away.length() > 1e-4:
                step = away.normalized() * ENGAGE_SPEED * 0.55 * dt
                self.entity.position = self.world.move(
                    self.entity.position, GUARD_RADIUS, step)
        else:
            # In the fighting band: strafe sideways, flipping periodically.
            if self._now >= self._strafe_switch_at:
                self._strafe_switch_at = self._now + self.rng.uniform(1.4, 2.4)
                self._strafe_dir = -self._strafe_dir
            fwd_x, fwd_z = rel.normalized().x, rel.normalized().z
            side = Vec3(-fwd_z * self._strafe_dir, 0, fwd_x * self._strafe_dir)
            step = side * STRAFE_SPEED * dt
            self.entity.position = self.world.move(
                self.entity.position, GUARD_RADIUS, step)

        if sees and dist <= FIRE_RANGE and self._now >= self._next_fire_at:
            self._next_fire_at = self._now + FIRE_INTERVAL_S \
                + self.rng.uniform(0.0, 0.4)
            self._fire(player_pos, bullets)

    def _fire(self, player_pos: Vec3, bullets: "BulletManager") -> None:
        origin = self.entity.position + Vec3(0.35, 0.4, 0) \
            + Vec3(math.sin(math.radians(self.entity.rotation_y)) * 0.6, 0,
                   math.cos(math.radians(self.entity.rotation_y)) * 0.6)
        target = player_pos + Vec3(0, 0.35, 0)
        direction = (target - origin)
        if direction.length() < 1e-4:
            return
        direction = direction.normalized()
        # Hand-aim spread: a running target is genuinely hard to hit.
        spread_yaw = self.rng.uniform(-0.035, 0.035)
        spread_pitch = self.rng.uniform(-0.02, 0.02)
        cy, sy = math.cos(spread_yaw), math.sin(spread_yaw)
        direction = Vec3(direction.x * cy - direction.z * sy,
                         direction.y + spread_pitch,
                         direction.x * sy + direction.z * cy).normalized()
        bullets.spawn(origin, direction * BULLET_SPEED, self.name)
        self.shots_fired += 1
        logger.info("Guard %s fired (total %d)", self.name, self.shots_fired)


# ---------------------------------------------------------------------------
# Projectiles
# ---------------------------------------------------------------------------
class _Bullet:
    __slots__ = ("entity", "velocity", "scored", "age", "shooter")

    def __init__(self, entity: Entity, velocity: Vec3, shooter: str) -> None:
        self.entity = entity
        self.velocity = velocity
        self.scored = False
        self.age = 0.0
        self.shooter = shooter


class BulletManager:
    """Flies guard projectiles; resolves hits, dodges and wall impacts."""

    def __init__(self, world: CollisionWorld) -> None:
        self.world = world
        self.bullets: List[_Bullet] = []
        self.total_spawned: int = 0
        # (points, label) callback for the HUD feed, set by the session.
        self.on_dodge: Optional[Callable[[int, str], None]] = None
        self.hits_on_player: int = 0

    def spawn(self, origin: Vec3, velocity: Vec3, shooter: str) -> None:
        ent = Entity(model="sphere", scale=0.22, position=origin,
                     color=color.rgb(255, 210, 90))
        self.bullets.append(_Bullet(ent, velocity, shooter))
        self.total_spawned += 1

    def tick(self, dt: float, player, stunt, bullet_time_active: bool) -> None:
        """Advance bullets by ``dt`` WORLD seconds.

        ``player`` is the PlayerController (position / take_damage);
        ``stunt`` is the StuntManager receiving Bullet Dodge events."""
        if dt <= 0:
            return
        chest = player.position + Vec3(0, 0.35, 0)
        alive: List[_Bullet] = []
        for b in self.bullets:
            b.age += dt
            b.entity.position += b.velocity * dt
            pos = b.entity.position
            dist = (pos - chest).length()

            if dist < BULLET_HIT_RADIUS and not player.dead:
                player.take_damage(BULLET_DAMAGE)
                self.hits_on_player += 1
                logger.info("Bullet from %s HIT the player (HP %.0f)",
                            b.shooter, player.hp)
                destroy(b.entity)
                continue
            if (bullet_time_active and not b.scored
                    and dist < DODGE_RADIUS and not player.dead):
                b.scored = True
                stunt.register("bullet_dodge")
                if self.on_dodge is not None:
                    self.on_dodge(STUNT_MATRIX["bullet_dodge"],
                                  "BULLET DODGE")
                logger.info("Bullet Dodge registered (bullet from %s)",
                            b.shooter)
            if b.age > BULLET_MAX_LIFE_S or self.world.point_blocked(pos):
                destroy(b.entity)
                continue
            alive.append(b)
        self.bullets = alive
