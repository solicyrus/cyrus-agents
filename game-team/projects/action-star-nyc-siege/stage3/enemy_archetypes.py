"""Enemy archetypes for Stage 3 (Action Star: NYC Siege 3D).

Cyrus's Stage-3 enemy table (approved 2026-10-27) plus the Floor-2
design reference (FLOOR2-DESIGN-REF.md):

  * EnforcerEnemy — heavy guard, shotgun + riot shield. INVULNERABLE
    from the front: frontal shots (and frontal melee) are registered
    as BLOCKED while the shield is up. Counters: slide-under shots
    (``low_attack=True`` — the shot passes under the shield) and
    flank/back shots (angle check against his facing). Defeating him
    via a bypass is the SHIELD BYPASS stunt (250 PTS, logic layer).
    Behaviour: advances aggressively on the player behind the shield.
  * MarksmanEnemy — laser sniper. Posts at a fixed (often raised)
    position, paints the player with a visible RED LASER, and after a
    continuous lock-on fires one high-damage shot. Breaking line of
    sight breaks the lock.
  * BossEnemy — the Syndicate Boss (Commander Vane), dual automatic
    pistols: burst fire, smoke grenades that genuinely block sight
    lines, cover-to-cover repositioning, and THREE phases keyed to his
    HP (66% / 33%): each phase fires faster and uses grenades more.
    ``hud_data()`` exposes {name, hp, max_hp, fraction, phase} for the
    HUD boss bar (stage3/boss_hud.py renders it).

All three share the Stage-1/2 patterns: the shared CollisionWorld for
movement/line-of-sight, Guard-style tick signatures
``tick(dt, player_pos, player_alive, bullets)``, an internal clock, and
the ``apply_stun(seconds)`` API the Data Center's rack discharges use.
Shots are real projectiles when a level1 BulletManager is supplied.
"""

from __future__ import annotations

import logging
import math
import os
import random
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ursina import Entity, Vec3, color, destroy  # noqa: E402

from level1.lobby_level import LIT, CollisionWorld, forward_from_yaw, yaw_towards  # noqa: E402
from level1.enemy_ai_3d import BULLET_SPEED  # noqa: E402

logger = logging.getLogger(__name__)

ENEMY_RADIUS = 0.5


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------
class _ArchetypeBase:
    """Common body / HP / stun / death plumbing for the archetypes."""

    def __init__(self, world: CollisionWorld, name: str, pos: Vec3,
                 max_hp: float, body_color, scale=(0.95, 1.9, 0.95),
                 facing_yaw: float = 0.0) -> None:
        self.world = world
        self.name = name
        self.max_hp = float(max_hp)
        self.hp = float(max_hp)
        self.alive = True
        self.state = "active"          # active | down | defenestrated
        self.radius = ENEMY_RADIUS
        self.entity = Entity(model="cube", scale=scale,
                             position=(float(pos.x), float(pos.y),
                                       float(pos.z)),
                             color=body_color, shader=LIT)
        self.entity.rotation_y = float(facing_yaw)
        self._now = 0.0
        self._stun_until = -1.0
        self.shots_fired = 0
        self.events: List[tuple] = []

    @property
    def position(self) -> Vec3:
        return self.entity.position

    @property
    def facing(self) -> Vec3:
        return forward_from_yaw(self.entity.rotation_y)

    @property
    def is_stunned(self) -> bool:
        return self._now < self._stun_until

    def apply_stun(self, seconds: float) -> None:
        """Electric stun (Data Center rack discharge). While stunned
        the enemy does not move, aim or fire."""
        if not self.alive or seconds <= 0:
            return
        self._stun_until = max(self._stun_until, self._now + float(seconds))
        logger.info("%s STUNNED for %.1fs", self.name, seconds)

    def _die(self, source: str) -> None:
        self.alive = False
        self.state = "down"
        self.entity.rotation_z = 88
        self.entity.y = 0.5
        self.entity.color = color.rgb32(70, 36, 36)
        logger.info("%s is DOWN (%s)", self.name, source)

    def _face(self, target: Vec3) -> None:
        rel = target - self.entity.position
        if math.hypot(rel.x, rel.z) > 1e-4:
            self.entity.rotation_y = yaw_towards(rel.x, rel.z)

    def _move_towards(self, target: Vec3, speed: float, dt: float) -> float:
        rel = target - self.entity.position
        rel.y = 0.0
        dist = rel.length()
        if dist < 1e-4:
            return 0.0
        step = rel.normalized() * min(speed * dt, dist)
        self.entity.position = self.world.move(self.entity.position,
                                               self.radius, step)
        return dist

    def _can_see(self, player_pos: Vec3, eye_h: float = 0.55) -> bool:
        eye = self.entity.position + Vec3(0, eye_h, 0)
        chest = player_pos + Vec3(0, 0.35, 0)
        if (chest - eye).length() > 34.0:
            return False
        return self.world.line_of_sight(eye, chest)


# ---------------------------------------------------------------------------
# Enforcer — shield heavy
# ---------------------------------------------------------------------------
ENFORCER_MAX_HP = 850.0        # FLOOR2-DESIGN-REF card: 850 HP
ENFORCER_ADVANCE_SPEED = 3.1
ENFORCER_KEEP_DISTANCE = 3.0   # stops advancing inside this range
SHOTGUN_RANGE = 10.0
SHOTGUN_PELLETS = 5
SHOTGUN_INTERVAL_S = 1.7
FRONTAL_COS = 0.42             # ~65 deg half-angle: the shield's arc


class EnforcerEnemy(_ArchetypeBase):
    """Heavy guard behind a ballistic riot shield (see module doc)."""

    def __init__(self, world: CollisionWorld, name: str, pos: Vec3,
                 facing_yaw: float = 0.0,
                 rng: Optional[random.Random] = None) -> None:
        super().__init__(world, name, pos, ENFORCER_MAX_HP,
                         color.rgb32(52, 62, 92), scale=(1.1, 1.95, 1.1),
                         facing_yaw=facing_yaw)
        self.rng = rng or random.Random(7)
        self.shield = Entity(model="cube", scale=(1.35, 1.65, 0.16),
                             position=(0, 0.05, 0.68), parent=self.entity,
                             color=color.rgb32(30, 34, 44), shader=LIT)
        self._shield_flash_ttl = 0.0
        self.blocked_shots = 0
        self._next_shot_at = 0.8

    # ------------------------------------------------------------- damage
    def _is_frontal(self, attacker_pos: Vec3) -> bool:
        """True when the attacker stands inside the shield's front arc."""
        to_attacker = attacker_pos - self.entity.position
        to_attacker.y = 0.0
        if to_attacker.length() < 1e-4:
            return False
        return self.facing.dot(to_attacker.normalized()) > FRONTAL_COS

    def take_shot_damage(self, dmg: float, shooter_pos: Vec3,
                         low_attack: bool = False) -> str:
        """A bullet arrives. Frontal + shield up + not a slide-under
        shot -> 'blocked' (no HP loss, the block is registered).
        Otherwise the damage lands; returns 'hit' or 'dead'."""
        if not self.alive:
            return "already_down"
        if self._is_frontal(shooter_pos) and not low_attack:
            self.blocked_shots += 1
            self._shield_flash_ttl = 0.12
            self.events.append(("blocked_shot", self._now))
            logger.info("%s BLOCKED a frontal shot (total %d)",
                        self.name, self.blocked_shots)
            return "blocked"
        self.hp = max(0.0, self.hp - float(dmg))
        logger.info("%s took %.0f shot damage -> HP %.0f",
                    self.name, dmg, self.hp)
        if self.hp <= 0.0:
            self._die("shot")
            return "dead"
        return "hit"

    def take_melee_damage(self, dmg: float, attacker_pos: Vec3,
                          vault: bool = False) -> str:
        """Melee: the shield blocks frontal strikes too — unless the
        attacker vaults the shield (Vault-Slam) or strikes his back."""
        if not self.alive:
            return "already_down"
        if self._is_frontal(attacker_pos) and not vault:
            self.blocked_shots += 1
            self._shield_flash_ttl = 0.12
            self.events.append(("blocked_melee", self._now))
            return "blocked"
        self.hp = max(0.0, self.hp - float(dmg))
        if self.hp <= 0.0:
            self._die("melee")
            return "dead"
        return "hit"

    # ---------------------------------------------------------------- tick
    def tick(self, dt: float, player_pos: Vec3, player_alive: bool = True,
             bullets=None) -> None:
        if dt <= 0 or not self.alive:
            return
        self._now += dt
        if self._shield_flash_ttl > 0:
            self._shield_flash_ttl -= dt
            self.shield.color = color.rgb32(120, 140, 170) \
                if self._shield_flash_ttl > 0 else color.rgb32(30, 34, 44)
        if self.is_stunned or not player_alive:
            return
        self._face(player_pos)
        dist = (player_pos - self.entity.position)
        dist.y = 0.0
        if dist.length() > ENFORCER_KEEP_DISTANCE:
            self._move_towards(player_pos, ENFORCER_ADVANCE_SPEED, dt)
        if bullets is not None and dist.length() <= SHOTGUN_RANGE \
                and self._now >= self._next_shot_at \
                and self._can_see(player_pos):
            self._next_shot_at = self._now + SHOTGUN_INTERVAL_S
            self._fire_shotgun(player_pos, bullets)

    def _fire_shotgun(self, player_pos: Vec3, bullets) -> None:
        origin = self.entity.position + Vec3(0, 0.35, 0) \
            + self.facing * 0.8
        target = player_pos + Vec3(0, 0.3, 0)
        base = (target - origin)
        if base.length() < 1e-4:
            return
        base = base.normalized()
        for _ in range(SHOTGUN_PELLETS):
            yaw = self.rng.uniform(-0.07, 0.07)
            pitch = self.rng.uniform(-0.03, 0.03)
            cy, sy = math.cos(yaw), math.sin(yaw)
            d = Vec3(base.x * cy - base.z * sy, base.y + pitch,
                     base.x * sy + base.z * cy).normalized()
            bullets.spawn(origin, d * BULLET_SPEED, self.name)
            self.shots_fired += 1
        logger.info("%s fired the shotgun (%d pellets)", self.name,
                    SHOTGUN_PELLETS)


# ---------------------------------------------------------------------------
# Marksman — laser sniper
# ---------------------------------------------------------------------------
MARKSMAN_MAX_HP = 150.0
MARKSMAN_LOCK_TIME_S = 1.5     # continuous LOS needed before the shot
MARKSMAN_SHOT_DAMAGE = 30.0
MARKSMAN_REFIRE_S = 1.1        # pause after a shot before re-locking


class MarksmanEnemy(_ArchetypeBase):
    """Laser sniper on a fixed post. The red laser is a real entity
    stretched from his muzzle to the player's chest every tick; the
    lock only builds while the shared world reports a clear sight line.
    """

    def __init__(self, world: CollisionWorld, name: str, pos: Vec3,
                 facing_yaw: float = 0.0) -> None:
        super().__init__(world, name, pos, MARKSMAN_MAX_HP,
                         color.rgb32(40, 44, 54), scale=(0.85, 1.85, 0.85),
                         facing_yaw=facing_yaw)
        self.lock_progress = 0.0
        self._refire_until = 0.0
        self.last_shot_hit: Optional[bool] = None
        # Damage sink: the session sets this to apply a landed shot
        # (e.g. the player's take_damage). None = shots are recorded
        # as events only (unit tests, scripted scenes).
        self.damage_sink = None
        # The laser: a thin red beam, hidden until he paints a target.
        self.laser_entity = Entity(model="cube", scale=(0.035, 0.035, 1.0),
                                   color=color.rgb32(255, 40, 40),
                                   enabled=False)
        self._tracer_ttl = 0.0
        self._tracer: Optional[Entity] = None

    @property
    def laser_active(self) -> bool:
        return bool(self.laser_entity.enabled)

    def _muzzle(self) -> Vec3:
        return self.entity.position + Vec3(0, 0.55, 0) + self.facing * 0.6

    def _aim_laser(self, target: Vec3) -> None:
        muzzle = self._muzzle()
        mid = (muzzle + target) / 2
        length = (target - muzzle).length()
        self.laser_entity.position = mid
        self.laser_entity.scale = (0.035, 0.035, max(0.1, length))
        self.laser_entity.look_at(target)
        self.laser_entity.enabled = True

    def tick(self, dt: float, player_pos: Vec3, player_alive: bool = True,
             bullets=None) -> None:
        if dt <= 0 or not self.alive:
            return
        self._now += dt
        if self._tracer is not None:
            self._tracer_ttl -= dt
            if self._tracer_ttl <= 0:
                destroy(self._tracer)
                self._tracer = None
        if self.is_stunned or not player_alive:
            self.laser_entity.enabled = False
            self.lock_progress = 0.0
            return
        self._face(player_pos)
        chest = player_pos + Vec3(0, 0.35, 0)
        if not self._can_see(player_pos):
            self.lock_progress = 0.0
            self.laser_entity.enabled = False
            return
        self._aim_laser(chest)
        if self._now < self._refire_until:
            return
        self.lock_progress += dt
        if self.lock_progress >= MARKSMAN_LOCK_TIME_S:
            self._fire(chest)

    def _fire(self, chest: Vec3) -> None:
        self.lock_progress = 0.0
        self._refire_until = self._now + MARKSMAN_REFIRE_S
        self.shots_fired += 1
        # Hit rule: the aim point IS the chest he tracked; the shot
        # lands when the sight line is still clear at the trigger
        # moment (a target that broke cover during the lock is missed
        # by the LOS re-check in tick — by construction he only fires
        # with a live sight line).
        hit = self.world.line_of_sight(self._muzzle(), chest)
        self.last_shot_hit = hit
        self.events.append(("marksman_fired", self._now, hit))
        muzzle = self._muzzle()
        tracer = Entity(model="cube",
                        scale=(0.05, 0.05,
                               max(0.1, (chest - muzzle).length())),
                        position=(muzzle + chest) / 2,
                        color=color.rgb32(255, 120, 90))
        tracer.look_at(chest)
        self._tracer = tracer
        self._tracer_ttl = 0.09
        if hit and self.damage_sink is not None:
            self.damage_sink(MARKSMAN_SHOT_DAMAGE)
        logger.info("%s FIRED (hit=%s, total %d)", self.name, hit,
                    self.shots_fired)


# ---------------------------------------------------------------------------
# Boss — the Syndicate Boss (Commander Vane)
# ---------------------------------------------------------------------------
BOSS_MAX_HP = 1200.0
BOSS_SPEED = 5.2
BOSS_FIRE_RANGE = 30.0
BURST_GAP_S = 0.09
PHASE_FIRE_INTERVAL = {1: 1.7, 2: 1.15, 3: 0.75}   # burst-to-burst
PHASE_BURST_SIZE = {1: 3, 2: 5, 3: 7}                # rounds per burst
PHASE_GRENADE_INTERVAL = {1: None, 2: 7.0, 3: 4.5}  # smoke grenades
PHASE_REPOSITION_S = {1: 6.0, 2: 4.5, 3: 3.2}        # cover-to-cover
SMOKE_RADIUS = 2.6
SMOKE_TTL_S = 6.0


class SmokeCloud:
    """One smoke-grenade cloud: a real entity + a sight blocker."""

    def __init__(self, position: Vec3, ttl: float = SMOKE_TTL_S) -> None:
        self.entity = Entity(model="sphere", scale=SMOKE_RADIUS * 2,
                             position=position,
                             color=color.rgba32(120, 120, 128, 110))
        self.entity.alpha = 0.45
        self.ttl = float(ttl)

    @property
    def center(self) -> Vec3:
        return self.entity.position

    def blocks_sight(self, a: Vec3, b: Vec3) -> bool:
        """Segment-vs-sphere: True when the cloud swallows the line."""
        ab = b - a
        denom = ab.dot(ab)
        if denom < 1e-9:
            return False
        t = max(0.0, min(1.0, (self.center - a).dot(ab) / denom))
        closest = a + ab * t
        return (closest - self.center).length() < SMOKE_RADIUS


class BossEnemy(_ArchetypeBase):
    """Syndicate Boss — three phases, bursts, smoke, cover movement."""

    DISPLAY_NAME = "SYNDICATE BOSS — COMMANDER VANE"

    def __init__(self, world: CollisionWorld, name: str, pos: Vec3,
                 cover_points: List[Vec3],
                 rng: Optional[random.Random] = None) -> None:
        super().__init__(world, name, pos, BOSS_MAX_HP,
                         color.rgb32(24, 24, 30), scale=(1.05, 2.0, 1.05))
        if not cover_points:
            raise ValueError("the boss needs at least one cover point")
        self.cover_points = [Vec3(p.x, pos.y, p.z) for p in cover_points]
        self._cover_index = 0
        self._reposition_at = PHASE_REPOSITION_S[1]
        self._burst_left = 0
        self._next_burst_at = 1.0
        self._next_shot_in_burst_at = 0.0
        self._next_grenade_at = 5.0
        self.smoke_clouds: List[SmokeCloud] = []
        self.grenades_thrown = 0
        self.rng = rng or random.Random(99)
        self._phase_seen = 1

    # ------------------------------------------------------------- phases
    @property
    def hp_fraction(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0

    @property
    def phase(self) -> int:
        frac = self.hp_fraction
        if frac > 2.0 / 3.0:
            return 1
        if frac > 1.0 / 3.0:
            return 2
        return 3

    def hud_data(self) -> dict:
        """The boss-bar contract for the HUD (stage3/boss_hud.py)."""
        return {
            "name": self.DISPLAY_NAME,
            "hp": round(self.hp, 1),
            "max_hp": self.max_hp,
            "fraction": self.hp_fraction,
            "phase": self.phase,
            "alive": self.alive,
        }

    def take_shot_damage(self, dmg: float, shooter_pos: Vec3 = None) -> str:
        if not self.alive:
            return "already_down"
        before = self.phase
        self.hp = max(0.0, self.hp - float(dmg))
        if self.hp <= 0.0:
            self._die("shot")
            return "dead"
        if self.phase != before:
            self.events.append(("phase_change", self._now, self.phase))
            logger.info("%s PHASE %d (HP %.0f/%.0f)", self.name,
                        self.phase, self.hp, self.max_hp)
        return "hit"

    def take_melee_damage(self, dmg: float,
                          attacker_pos: Vec3 = None) -> str:
        return self.take_shot_damage(dmg, attacker_pos)

    # ------------------------------------------------------------- grenades
    def throw_smoke_grenade(self, target_pos: Vec3) -> SmokeCloud:
        """Throw a smoke grenade landing at ``target_pos``: the cloud
        blocks sight lines through it for SMOKE_TTL_S seconds."""
        cloud = SmokeCloud(Vec3(float(target_pos.x), 1.2,
                                float(target_pos.z)))
        self.smoke_clouds.append(cloud)
        self.grenades_thrown += 1
        self.events.append(("smoke_grenade", self._now))
        logger.info("%s threw a smoke grenade (total %d)", self.name,
                    self.grenades_thrown)
        return cloud

    def sight_blocked(self, a: Vec3, b: Vec3) -> bool:
        """True when the world OR one of his smoke clouds blocks a->b."""
        if not self.world.line_of_sight(a, b):
            return True
        return any(c.blocks_sight(a, b) for c in self.smoke_clouds)

    # ---------------------------------------------------------------- tick
    def tick(self, dt: float, player_pos: Vec3, player_alive: bool = True,
             bullets=None) -> None:
        if dt <= 0 or not self.alive:
            return
        self._now += dt
        # Smoke expiry runs even while he is stunned.
        alive_clouds = []
        for cloud in self.smoke_clouds:
            cloud.ttl -= dt
            if cloud.ttl > 0:
                alive_clouds.append(cloud)
            else:
                destroy(cloud.entity)
        self.smoke_clouds = alive_clouds
        if self.is_stunned or not player_alive:
            return

        phase = self.phase
        if phase != self._phase_seen:
            self._phase_seen = phase
            self._reposition_at = self._now  # move NOW on a phase change

        # Cover-to-cover repositioning.
        target = self.cover_points[self._cover_index]
        if self._now >= self._reposition_at:
            self._cover_index = (self._cover_index + 1) \
                % len(self.cover_points)
            self._reposition_at = self._now + PHASE_REPOSITION_S[phase]
            target = self.cover_points[self._cover_index]
        dist_to_cover = self._move_towards(target, BOSS_SPEED, dt) \
            if (target - self.entity.position).length() > 1.2 else 0.0
        self._face(player_pos)

        eye = self.entity.position + Vec3(0, 0.6, 0)
        chest = player_pos + Vec3(0, 0.35, 0)
        dist = (chest - eye).length()
        sees = dist <= BOSS_FIRE_RANGE and not self.sight_blocked(eye, chest)

        # Smoke grenades (phase 2+): drop one between him and the player
        # when he can be seen — he fights from behind his own smoke.
        interval = PHASE_GRENADE_INTERVAL[phase]
        if interval is not None and self._now >= self._next_grenade_at:
            self._next_grenade_at = self._now + interval
            mid = (self.entity.position + player_pos) / 2
            self.throw_smoke_grenade(mid)

        # Burst fire with the dual automatics.
        if bullets is not None and sees:
            if self._burst_left <= 0 and self._now >= self._next_burst_at:
                self._burst_left = PHASE_BURST_SIZE[phase]
                self._next_shot_in_burst_at = self._now
            if self._burst_left > 0 \
                    and self._now >= self._next_shot_in_burst_at:
                self._next_shot_in_burst_at = self._now + BURST_GAP_S
                self._burst_left -= 1
                self._fire_one(player_pos, bullets)
                if self._burst_left == 0:
                    self._next_burst_at = self._now \
                        + PHASE_FIRE_INTERVAL[phase]
        _ = dist_to_cover  # movement distance is diagnostic only

    def _fire_one(self, player_pos: Vec3, bullets) -> None:
        origin = self.entity.position + Vec3(0, 0.45, 0) + self.facing * 0.7
        target = player_pos + Vec3(0, 0.35, 0)
        direction = (target - origin)
        if direction.length() < 1e-4:
            return
        direction = direction.normalized()
        spread = self.rng.uniform(-0.03, 0.03)
        cy, sy = math.cos(spread), math.sin(spread)
        direction = Vec3(direction.x * cy - direction.z * sy,
                         direction.y, direction.x * sy
                         + direction.z * cy).normalized()
        bullets.spawn(origin, direction * BULLET_SPEED, self.name)
        self.shots_fired += 1
