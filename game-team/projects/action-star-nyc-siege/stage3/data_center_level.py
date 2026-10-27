"""DataCenterLevel — Floor 2 of the tower (Action Star: NYC Siege 3D).

Stage 3, Cyrus's design (approved 2026-10-27): a tight, high-tech floor —
corridors between server-rack rows, smoked-glass meeting rooms, a
monitoring wall — with two signature interactive systems:

  * SERVER HAZARDS: the racks are live electrical hardware. Shooting a
    rack sparks it; when a rack's integrity fails it discharges — an
    electric shock that STUNS every enemy inside SHOCK_RADIUS (enemies
    expose ``apply_stun(seconds)``; all Stage-3 archetypes do). A rack
    discharges once, then stays burnt-out cover.
  * SPRINKLERS: sustained gunfire in one quadrant (SHOT_THRESHOLD shots
    inside SHOT_WINDOW_S) trips the fire system for that zone: droplet
    entities rain from the ceiling, a water film covers the camera and
    the level's ``visibility_factor`` drops to 0.55 while active.

Cover on this floor is partly DESTRUCTIBLE (stage3.destructibles):
wooden desks and plaster columns shatter under fire.

Collision: the shared CollisionWorld from level1 (one model for rays,
line of sight and movement) — smoked-glass walls are ordinary solids in
it, so bullets genuinely stop at the glass.

Target time for this floor: 75 s (Cyrus 2026-10-27).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ursina import AmbientLight, DirectionalLight, Entity, PointLight, Vec3  # noqa: E402
from ursina import camera, color  # noqa: E402

from level1.lobby_level import LIT, CollisionWorld, Solid  # noqa: E402
from stage3.destructibles import DestructibleCover  # noqa: E402

logger = logging.getLogger(__name__)

# Floor target time — approved by Cyrus 2026-10-27.
TARGET_TIME_S = 75.0

# Interior dimensions (faces); characters move in XZ inside these.
ROOM_MIN_X, ROOM_MAX_X = -20.0, 20.0
ROOM_MIN_Z, ROOM_MAX_Z = -13.0, 13.0
WALL_HEIGHT = 6.0
WALL_THICKNESS = 1.0

# Server hazard tuning.
RACK_MAX_HP = 60.0
SHOCK_RADIUS = 4.5            # units around a discharging rack
SHOCK_STUN_S = 3.0            # stun duration applied to nearby enemies

# Sprinkler tuning.
SHOT_WINDOW_S = 5.0           # trailing window for "sustained gunfire"
SHOT_THRESHOLD = 6            # shots inside the window trip the system
SPRINKLER_DURATION_S = 12.0
SPRINKLER_COOLDOWN_S = 8.0
SPRINKLER_VISIBILITY = 0.55   # visibility_factor while the zone is wet
DROPLETS_PER_ZONE = 40

# Palette — cool steel/glass data floor with hot rack accents.
COL_FLOOR = color.rgb(52, 56, 64)
COL_WALL = color.rgb(104, 112, 124)
COL_RACK = color.rgb(38, 42, 52)
COL_RACK_FACE = color.rgb(24, 140, 130)
COL_RACK_BURNT = color.rgb(16, 16, 18)
COL_GLASS_SMOKED = color.rgba(52, 66, 80, 110)
COL_DESK_WOOD = color.rgb(116, 84, 54)
COL_PLASTER = color.rgb(178, 172, 158)
COL_SCREEN = color.rgb(120, 220, 255)
COL_CEILING = color.rgb(40, 42, 48)
COL_SPARK = color.rgb(255, 214, 90)
COL_WATER = color.rgba(140, 180, 230, 120)


class ServerRack:
    """One live server rack: solid cover with an electric secret.

    ``take_shot_damage(dmg)`` is the shooter's entry point (the session
    routes hitscan cover hits here, exactly like guard hits). Sparks fly
    on every hit; the hit that empties the rack's integrity triggers the
    discharge: enemies inside SHOCK_RADIUS are stunned via their
    ``apply_stun`` API.
    """

    def __init__(self, level: "DataCenterLevel", name: str,
                 cx: float, cz: float) -> None:
        self.level = level
        self.name = name
        self.hp = RACK_MAX_HP
        self.discharged = False
        self.entity = Entity(model="cube", scale=(1.6, 2.4, 2.8),
                             position=(cx, 1.2, cz), color=COL_RACK,
                             shader=LIT)
        self._face = Entity(model="cube", scale=(0.1, 2.0, 2.4),
                            position=(0.83, 0, 0), parent=self.entity,
                            color=COL_RACK_FACE, shader=LIT)
        self.solid = level.world.add(Solid(name=name, cx=cx, cz=cz,
                                           sx=1.6, sy=2.4, sz=2.8))

    @property
    def position(self) -> Vec3:
        return self.entity.position

    def take_shot_damage(self, dmg: float) -> dict:
        """Bullet hit on the rack. Returns a result dict with the
        discharge outcome: {"hp", "shock_triggered", "stunned": [names]}.
        """
        if dmg <= 0:
            return {"hp": self.hp, "shock_triggered": False, "stunned": []}
        self.level.spawn_sparks(self.entity.position)
        if self.discharged:
            return {"hp": self.hp, "shock_triggered": False, "stunned": []}
        self.hp = max(0.0, self.hp - float(dmg))
        logger.info("Rack %s took %.0f damage -> HP %.0f",
                    self.name, dmg, self.hp)
        if self.hp > 0.0:
            return {"hp": self.hp, "shock_triggered": False, "stunned": []}
        return {"hp": self.hp, "shock_triggered": True,
                "stunned": self._discharge()}

    def _discharge(self) -> List[str]:
        """The electric shock: stun every registered enemy in radius."""
        self.discharged = True
        self.entity.color = COL_RACK_BURNT
        self._face.color = color.rgb(30, 30, 30)
        self.level.spawn_sparks(self.entity.position, count=10)
        stunned: List[str] = []
        origin = Vec3(self.entity.x, 0.0, self.entity.z)
        for enemy in self.level.enemies:
            if not getattr(enemy, "alive", True):
                continue
            epos = enemy.position
            flat = Vec3(float(epos.x), 0.0, float(epos.z))
            if (flat - origin).length() <= SHOCK_RADIUS \
                    and hasattr(enemy, "apply_stun"):
                enemy.apply_stun(SHOCK_STUN_S)
                stunned.append(getattr(enemy, "name", "?"))
        logger.info("Rack %s DISCHARGED — stunned: %s", self.name, stunned)
        return stunned


class DataCenterLevel:
    """Builds Floor 2 and owns its hazards (racks + sprinklers)."""

    TARGET_TIME_S = TARGET_TIME_S

    def __init__(self) -> None:
        self.world = CollisionWorld()
        self.entities: List[Entity] = []
        self.enemies: List = []            # session-registered, for shocks
        self.racks: List[ServerRack] = []
        self.covers: List[DestructibleCover] = []
        self._now = 0.0
        self._transients: List[dict] = []  # spark bursts {entity, ttl}
        self._shot_log: List[Tuple[Tuple[int, int], float]] = []
        self._sprinkler_zone: Optional[Tuple[int, int]] = None
        self._sprinkler_until = 0.0
        self._sprinkler_cooldown_until = 0.0
        self._droplets: List[Entity] = []
        self._droplet_speeds: List[float] = []
        self._build_shell()
        self._build_racks()
        self._build_glass_rooms()
        self._build_cover()
        self._build_sprinkler_rig()
        self._build_lights()
        logger.info("DataCenter built: %d solids, %d racks",
                    len(self.world.solids), len(self.racks))

    # ------------------------------------------------------------- registry
    def register_enemy(self, enemy) -> None:
        """The session registers the floor's enemies so rack discharges
        can find them (duck-typed: needs .position, .alive, .apply_stun).
        """
        self.enemies.append(enemy)

    # ------------------------------------------------------------- helpers
    def _solid(self, name: str, cx: float, cz: float,
               size: Tuple[float, float, float], solid_color,
               y_base: float = 0.0) -> Entity:
        sx, sy, sz = size
        ent = Entity(model="cube", scale=(sx, sy, sz),
                     position=(cx, y_base + sy / 2.0, cz),
                     color=solid_color, shader=LIT)
        self.entities.append(ent)
        self.world.add(Solid(name=name, cx=cx, cz=cz, sx=sx, sy=sy, sz=sz,
                             y0=y_base))
        return ent

    def _visual(self, cx: float, cy: float, cz: float,
                size: Tuple[float, float, float], visual_color,
                lit: bool = True) -> Entity:
        ent = Entity(model="cube", scale=size, position=(cx, cy, cz),
                     color=visual_color, shader=LIT if lit else None)
        self.entities.append(ent)
        return ent

    # ------------------------------------------------------------ geometry
    def _build_shell(self) -> None:
        self._visual(0, -0.25, 0, (44, 0.5, 30), COL_FLOOR)
        self._visual(0, WALL_HEIGHT + 0.25, 0, (44, 0.5, 30), COL_CEILING)
        t = WALL_THICKNESS
        self._solid("wall_north", 0, ROOM_MAX_Z + t / 2,
                    (44, WALL_HEIGHT, t), COL_WALL)
        self._solid("wall_south", 0, -ROOM_MAX_Z - t / 2,
                    (44, WALL_HEIGHT, t), COL_WALL)
        self._solid("wall_east", ROOM_MAX_X + t / 2, 0,
                    (t, WALL_HEIGHT, 30), COL_WALL)
        self._solid("wall_west", -ROOM_MAX_X - t / 2, 0,
                    (t, WALL_HEIGHT, 30), COL_WALL)
        # Monitoring wall: bright screens along the north wall (visual).
        for x in (-13.5, -4.5, 4.5, 13.5):
            self._visual(x, 3.4, ROOM_MAX_Z - 0.08, (7.6, 3.2, 0.12),
                         COL_SCREEN, lit=False)
        # Corridor partition walls (half height) in the east half — they
        # bend the approach into the meeting-room area.
        self._solid("partition_a", 12.0, 5.0, (0.7, 3.0, 9.0), COL_PLASTER)
        self._solid("partition_b", 12.0, -8.5, (0.7, 3.0, 6.0), COL_PLASTER)

    def _build_racks(self) -> None:
        """Two rack rows in the west half — the floor's signature cover
        and its electrical hazard."""
        for row_x in (-13.0, -9.5):
            for i, z in enumerate((-8.0, -4.0, 0.0, 4.0, 8.0)):
                rack = ServerRack(self, f"rack_{row_x:+.0f}_{i}", row_x, z)
                self.racks.append(rack)
                self.entities.append(rack.entity)

    def _build_glass_rooms(self) -> None:
        """Smoked-glass meeting room: a glass partition at x = 6 with a
        meeting table behind it. The glass is a real collision solid —
        bullets stop at it (QA gate a)."""
        for i, z in enumerate((-4.35, 0.0, 4.35)):
            glass = self._solid(f"smoked_glass_partition_{i}", 6.0, z,
                                (0.35, 4.6, 4.2), COL_GLASS_SMOKED)
            glass.alpha = 0.45
        # Steel posts capping the glass run.
        self._solid("glass_post_south", 6.0, -6.9, (0.5, WALL_HEIGHT, 0.7),
                    COL_WALL)
        self._solid("glass_post_north", 6.0, 6.9, (0.5, WALL_HEIGHT, 0.7),
                    COL_WALL)
        # Meeting table + bench seating inside the room (visual set
        # dressing behind the glass; the table is low solid cover).
        self._solid("meeting_table", 11.0, 0.0, (4.6, 1.05, 2.4),
                    COL_DESK_WOOD)
        for z in (-2.3, 2.3):
            self._visual(11.0, 0.35, z, (4.2, 0.7, 0.9), COL_WALL)

    def _build_cover(self) -> None:
        """Destructible cover: wooden desks mid-room, plaster columns."""
        desk1 = DestructibleCover(self.world, "desk_wood_west", -2.0, -6.0,
                                  (3.4, 1.1, 1.5), COL_DESK_WOOD, hp=70.0)
        desk2 = DestructibleCover(self.world, "desk_wood_east", 3.0, 7.5,
                                  (3.4, 1.1, 1.5), COL_DESK_WOOD, hp=70.0)
        col1 = DestructibleCover(self.world, "column_plaster_a", -3.5, 3.0,
                                 (1.1, WALL_HEIGHT, 1.1), COL_PLASTER,
                                 hp=110.0)
        col2 = DestructibleCover(self.world, "column_plaster_b", 15.5, -3.0,
                                 (1.1, WALL_HEIGHT, 1.1), COL_PLASTER,
                                 hp=110.0)
        self.covers.extend([desk1, desk2, col1, col2])
        self.entities.extend(c.entity for c in self.covers)

    def _build_sprinkler_rig(self) -> None:
        """Droplet pool (one per zone layout, recycled) + camera film."""
        for i in range(DROPLETS_PER_ZONE):
            drop = Entity(model="cube", scale=(0.05, 0.5, 0.05),
                          color=COL_WATER, enabled=False)
            self._droplets.append(drop)
            self._droplet_speeds.append(7.0 + (i % 5) * 1.3)
            self.entities.append(drop)
        # Water film over the camera while the sprinklers run.
        self._water_film = Entity(parent=camera.ui, model="quad",
                                  scale=(2.2, 1.3), color=COL_WATER,
                                  enabled=False)
        self.entities.append(self._water_film)

    def _build_lights(self) -> None:
        key = DirectionalLight(shadows=False)
        key.rotation = (52, -18, 0)
        key.color = color.rgb(200, 216, 255)
        fill = AmbientLight()
        fill.color = color.rgb(58, 64, 78)
        strip = PointLight()
        strip.position = (0, 5.2, 0)
        strip.color = color.rgb(150, 200, 255)
        strip.range = 36
        self.entities.extend([key, fill, strip])

    # -------------------------------------------------------- spark effects
    def spawn_sparks(self, at: Vec3, count: int = 4) -> None:
        """A short-lived burst of spark cubes at a hit point."""
        for i in range(count):
            spark = Entity(model="cube", scale=0.13,
                           position=(float(at.x) + (i % 3 - 1) * 0.3,
                                     float(at.y) + (i % 2) * 0.5,
                                     float(at.z) + (i % 4 - 1.5) * 0.3),
                           color=COL_SPARK)
            self._transients.append({"entity": spark, "ttl": 0.22})
            self.entities.append(spark)

    # ------------------------------------------------------------ sprinklers
    @staticmethod
    def _zone_of(pos: Vec3) -> Tuple[int, int]:
        return (0 if pos.x < 0 else 1, 0 if pos.z < 0 else 1)

    def note_gunfire(self, pos: Vec3) -> None:
        """The session reports every shot fired on the floor; sustained
        fire inside one quadrant trips that zone's sprinklers."""
        self._shot_log.append((self._zone_of(pos), self._now))

    @property
    def sprinkler_active(self) -> bool:
        return self._sprinkler_zone is not None

    @property
    def sprinkler_zone(self) -> Optional[Tuple[int, int]]:
        return self._sprinkler_zone

    @property
    def visibility_factor(self) -> float:
        """1.0 normally; SPRINKLER_VISIBILITY while a zone is wet —
        sessions/AI consume this; the smoke test asserts the state."""
        return SPRINKLER_VISIBILITY if self.sprinkler_active else 1.0

    def _update_sprinklers(self, dt: float) -> None:
        cutoff = self._now - SHOT_WINDOW_S
        self._shot_log = [s for s in self._shot_log if s[1] >= cutoff]
        if self._sprinkler_zone is not None:
            if self._now >= self._sprinkler_until:
                self._sprinkler_zone = None
                self._sprinkler_cooldown_until = self._now \
                    + SPRINKLER_COOLDOWN_S
                for drop in self._droplets:
                    drop.enabled = False
                self._water_film.enabled = False
                logger.info("Sprinklers OFF")
            else:
                self._rain(dt)
            return
        if self._now < self._sprinkler_cooldown_until:
            return
        counts: Dict[Tuple[int, int], int] = {}
        for zone, _ts in self._shot_log:
            counts[zone] = counts.get(zone, 0) + 1
        for zone, n in counts.items():
            if n >= SHOT_THRESHOLD:
                self._activate_sprinklers(zone)
                break

    def _activate_sprinklers(self, zone: Tuple[int, int]) -> None:
        self._sprinkler_zone = zone
        self._sprinkler_until = self._now + SPRINKLER_DURATION_S
        cx = -10.0 if zone[0] == 0 else 10.0
        cz = -6.5 if zone[1] == 0 else 6.5
        for i, drop in enumerate(self._droplets):
            drop.enabled = True
            drop.position = (cx + (i % 8 - 3.5) * 2.2,
                             WALL_HEIGHT - 0.3 - (i % 6) * 0.8,
                             cz + (i // 8 - 2.5) * 2.2)
        self._water_film.enabled = True
        logger.info("Sprinklers ON in zone %s — visibility %.2f",
                    zone, SPRINKLER_VISIBILITY)

    def _rain(self, dt: float) -> None:
        for i, drop in enumerate(self._droplets):
            drop.y -= self._droplet_speeds[i] * dt
            if drop.y < 0.3:
                drop.y = WALL_HEIGHT - 0.3

    # ------------------------------------------------------------------ tick
    def tick(self, dt: float) -> None:
        """Advance hazard effects: sparks, cover flashes, sprinklers."""
        if dt <= 0:
            return
        self._now += dt
        alive = []
        for item in self._transients:
            item["ttl"] -= dt
            if item["ttl"] > 0:
                alive.append(item)
            else:
                item["entity"].enabled = False
        self._transients = alive
        for cover in self.covers:
            cover.tick(dt)
        self._update_sprinklers(dt)
