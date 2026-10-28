"""PenthouseLevel — Floor 3 of the tower (Action Star: NYC Siege 3D).

Stage 3 finale, Cyrus's design (approved 2026-10-27): a luxury duplex
hall with 360-degree panoramic BREAKABLE windows, an infinity pool, and
a spiral staircase rising to the roof helipad where the escape — and
the Syndicate Boss — wait.

Signature systems:

  * BREAKABLE PANORAMIC WINDOWS: every pane is a WindowPane — a real
    CollisionWorld solid of glass. ``break_pane()`` removes the solid
    (state change in the one collision model) and shatters the visual.
    ``throw_enemy_out(enemy, stunt)`` throws a defeated enemy through
    the nearest pane and registers the DEFENESTRATION stunt (500 PTS,
    the highest-value move in the game) into the StuntManager.
  * ROOF WIND: on the helipad deck a strong cross-wind blows. The level
    exposes ``wind_at(pos)`` (the drift vector) and
    ``move_speed_factor_at(pos, move_dir)`` (fighting the wind is
    slower, riding it is faster), and its dust particles visibly drift
    with the wind in ``tick``. The movement consumer (player controller
    / session) integrates these — they are real level state, measured
    by the Stage-3 smoke test.

Honest scope note (same as level1): the collision model is planar per
floor plate. The spiral staircase is built geometry (14 steps rising
along the east wall to the roof plate at ROOF_Y); vertical traversal
physics between plates is a session concern, not faked here.

Target time for this floor: 105 s (Cyrus 2026-10-27), boss included.
"""

from __future__ import annotations

import logging
import math
import os
import sys
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ursina import AmbientLight, DirectionalLight, Entity, PointLight, Vec3  # noqa: E402
from ursina import color  # noqa: E402

from level1.lobby_level import LIT, CollisionWorld, Solid  # noqa: E402
from stage3.destructibles import DestructibleCover  # noqa: E402

logger = logging.getLogger(__name__)

# Floor target time — approved by Cyrus 2026-10-27 (boss fight included).
TARGET_TIME_S = 105.0

ROOM_MIN_X, ROOM_MAX_X = -23.0, 23.0
ROOM_MIN_Z, ROOM_MAX_Z = -16.0, 16.0
WALL_HEIGHT = 7.0
WALL_THICKNESS = 1.0
ROOF_Y = 7.0                    # helipad deck plate height
ROOF_DECK_MIN_Z = 8.0           # deck occupies z in [ROOF_DECK_MIN_Z, MAX]

# Roof wind — a hard cross-wind over the helipad.
WIND_VECTOR = Vec3(6.0, 0.0, -2.5)
WIND_AGAINST_FACTOR = 0.62      # moving straight against the wind
WIND_WITH_FACTOR = 1.38         # moving straight with it

# Palette — warm luxury against a night-blue city glass line.
COL_FLOOR = color.rgb32(74, 62, 50)
COL_WALL = color.rgb32(128, 112, 92)
COL_GLASS = color.rgba32(150, 200, 235, 90)
COL_GOLD = color.rgb32(198, 158, 60)
COL_POOL = color.rgba32(70, 150, 220, 120)
COL_POOL_RIM = color.rgb32(210, 200, 180)
COL_STAIRS = color.rgb32(96, 80, 64)
COL_HELIPAD = color.rgb32(58, 60, 66)
COL_DESK_WOOD = color.rgb32(116, 84, 54)
COL_PLASTER = color.rgb32(178, 172, 158)
COL_CITY = color.rgb32(28, 36, 60)


class WindowPane:
    """One panoramic window pane: glass solid that can shatter."""

    def __init__(self, level: "PenthouseLevel", name: str, cx: float,
                 cz: float, size: Tuple[float, float, float],
                 outward: Vec3, y_base: float = 0.0) -> None:
        sx, sy, sz = size
        self.level = level
        self.name = name
        self.outward = outward        # unit vector pointing out of the tower
        self.broken = False
        self.entity = Entity(model="cube", scale=(sx, sy, sz),
                             position=(cx, y_base + sy / 2.0, cz),
                             color=COL_GLASS, shader=LIT)
        self.entity.alpha = 0.35
        self.solid = level.world.add(Solid(name=name, cx=cx, cz=cz, sx=sx,
                                           sy=sy, sz=sz, y0=y_base))
        self.shards: List[Entity] = []

    @property
    def position(self) -> Vec3:
        return self.entity.position

    def break_pane(self) -> bool:
        """Shatter the pane: the solid leaves the world (rays and
        movement now pass), the glass visual goes, shards drop inside.
        Returns True only for the hit that actually breaks it."""
        if self.broken:
            return False  # already open — nothing new happened
        self.broken = True
        if self.solid in self.level.world.solids:
            self.level.world.solids.remove(self.solid)
        self.entity.enabled = False
        cx, cz = float(self.entity.x), float(self.entity.z)
        base_y = float(self.solid.y0)
        for i, (ox, oz) in enumerate(((-1.2, 0.2), (0.4, -0.6), (1.4, 0.5),
                                      (-0.3, 0.9), (0.9, -0.2))):
            shard = Entity(model="cube", scale=(0.5, 0.06, 0.4),
                           position=(cx - self.outward.x * 0.8 + ox,
                                     base_y + 0.05,
                                     cz - self.outward.z * 0.8 + oz),
                           rotation_y=i * 41.0, color=COL_GLASS,
                           shader=LIT)
            self.shards.append(shard)
        logger.info("Window pane %s SHATTERED", self.name)
        return True


class PenthouseLevel:
    """Builds Floor 3 (hall + roof deck) and owns windows + wind."""

    TARGET_TIME_S = TARGET_TIME_S

    def __init__(self) -> None:
        self.world = CollisionWorld()
        self.entities: List[Entity] = []
        self.panes: List[WindowPane] = []
        self.covers: List[DestructibleCover] = []
        self._dust: List[Entity] = []
        self._build_shell()
        self._build_windows()
        self._build_pool()
        self._build_staircase_and_roof()
        self._build_cover()
        self._build_lights()
        logger.info("Penthouse built: %d solids, %d window panes",
                    len(self.world.solids), len(self.panes))

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
        self._visual(0, -0.25, 0, (50, 0.5, 36), COL_FLOOR)
        # North + west walls are solid; south + east are the glass line.
        t = WALL_THICKNESS
        self._solid("wall_north", 0, ROOM_MAX_Z + t / 2,
                    (50, WALL_HEIGHT, t), COL_WALL)
        self._solid("wall_west", -ROOM_MAX_X - t / 2, 0,
                    (t, WALL_HEIGHT, 36), COL_WALL)
        # Marble mullions between the panoramic panes.
        for x in (-23.0, -15.33, -7.67, 0.0, 7.67, 15.33, 23.0):
            self._solid(f"mullion_south_{x:+.0f}", x, -ROOM_MAX_Z - t / 2,
                        (0.6, WALL_HEIGHT, t), COL_WALL)
        for z in (-16.0, -8.0, 0.0, 8.0, 16.0):
            self._solid(f"mullion_east_{z:+.0f}", ROOM_MAX_X + t / 2, z,
                        (t, WALL_HEIGHT, 0.6), COL_WALL)
        # City backdrop far below the glass line (visual only).
        self._visual(0, -14, -34, (90, 26, 1), COL_CITY, lit=False)
        self._visual(40, -12, 0, (1, 30, 80), COL_CITY, lit=False)

    def _build_windows(self) -> None:
        """Panoramic panes: 6 along the south wall, 4 along the east."""
        z = -ROOM_MAX_Z - WALL_THICKNESS / 2
        centres_south = (-19.17, -11.5, -3.83, 3.83, 11.5, 19.17)
        for i, x in enumerate(centres_south):
            pane = WindowPane(self, f"window_south_{i}", x, z,
                              (7.0, 5.6, 0.3), outward=Vec3(0, 0, -1))
            self.panes.append(pane)
            self.entities.append(pane.entity)
        x = ROOM_MAX_X + WALL_THICKNESS / 2
        for i, wz in enumerate((-12.0, -4.0, 4.0, 12.0)):
            pane = WindowPane(self, f"window_east_{i}", x, wz,
                              (0.3, 5.6, 7.4), outward=Vec3(1, 0, 0))
            self.panes.append(pane)
            self.entities.append(pane.entity)

    def _build_pool(self) -> None:
        """Infinity pool on the west side: water visual + rim cover."""
        self._visual(-16.5, 0.32, 2.0, (9.0, 0.5, 12.0), COL_POOL,
                     lit=False)
        self._solid("pool_rim_south", -16.5, -4.3, (9.6, 0.6, 0.7),
                    COL_POOL_RIM)
        self._solid("pool_rim_north", -16.5, 8.3, (9.6, 0.6, 0.7),
                    COL_POOL_RIM)
        self._solid("pool_rim_west", -21.3, 2.0, (0.7, 0.6, 13.3),
                    COL_POOL_RIM)

    def _build_staircase_and_roof(self) -> None:
        """Spiral staircase (visual steps, east wall) + roof helipad."""
        steps = 14
        for i in range(steps):
            frac = i / (steps - 1)
            y = 0.35 + frac * (ROOF_Y - 0.35)
            z = -10.0 + frac * 16.0
            self._visual(20.6, y, z, (3.4, 0.3, 1.6), COL_STAIRS)
        # Roof deck plate over the north strip + helipad marking.
        self._visual(0, ROOF_Y + 0.1, (ROOF_DECK_MIN_Z + ROOM_MAX_Z) / 2,
                     (48, 0.2, ROOM_MAX_Z - ROOF_DECK_MIN_Z), COL_HELIPAD)
        pad = Entity(model="circle", scale=(7.0, 7.0, 1.0),
                     rotation_x=90,
                     position=(0, ROOF_Y + 0.22, 12.0), color=COL_GOLD,
                     shader=LIT)
        self.entities.append(pad)
        # Wind-blown dust motes over the deck (recycled in tick).
        for i in range(24):
            mote = Entity(model="cube", scale=0.09,
                          position=(-20 + (i * 1.7) % 40, ROOF_Y + 0.8,
                                    9.0 + (i % 5) * 1.6),
                          color=color.rgb32(200, 190, 170))
            self._dust.append(mote)
            self.entities.append(mote)

    def _build_cover(self) -> None:
        """Destructible cover in the hall: a bar counter + plaster
        columns (the penthouse furniture shatters like Floor 2's)."""
        bar = DestructibleCover(self.world, "penthouse_bar", 4.0, -6.0,
                                (6.0, 1.15, 1.6), COL_DESK_WOOD, hp=80.0)
        col = DestructibleCover(self.world, "penthouse_column", -6.0, 6.0,
                                (1.1, WALL_HEIGHT, 1.1), COL_PLASTER,
                                hp=110.0)
        self.covers.extend([bar, col])
        self.entities.extend(c.entity for c in self.covers)

    def _build_lights(self) -> None:
        key = DirectionalLight(shadows=False)
        key.rotation = (40, 25, 0)
        key.color = color.rgb32(255, 224, 180)
        fill = AmbientLight()
        fill.color = color.rgb32(66, 74, 96)
        chandelier = PointLight()
        chandelier.position = (0, 6.2, -2)
        chandelier.color = color.rgb32(255, 196, 130)
        chandelier.range = 38
        roof_wash = PointLight()
        roof_wash.position = (0, ROOF_Y + 3.5, 12)
        roof_wash.color = color.rgb32(150, 180, 255)
        roof_wash.range = 24
        self.entities.extend([key, fill, chandelier, roof_wash])

    # ----------------------------------------------------------------- wind
    def on_roof_deck(self, pos: Vec3) -> bool:
        """True when a position is up on the helipad deck plate."""
        return pos.y >= ROOF_Y - 0.5 and pos.z >= ROOF_DECK_MIN_Z

    def wind_at(self, pos: Vec3) -> Vec3:
        """The wind drift vector at a position (zero off the deck)."""
        if self.on_roof_deck(pos):
            return Vec3(WIND_VECTOR.x, WIND_VECTOR.y, WIND_VECTOR.z)
        return Vec3(0, 0, 0)

    def move_speed_factor_at(self, pos: Vec3, move_dir: Vec3) -> float:
        """Movement speed multiplier from the roof wind: pushing
        against it costs speed, riding it gains speed, crossing it is
        near-neutral. 1.0 anywhere off the deck."""
        wind = self.wind_at(pos)
        if wind.length() < 1e-6 or move_dir.length() < 1e-6:
            return 1.0
        alignment = move_dir.normalized().dot(wind.normalized())
        lo, hi = WIND_AGAINST_FACTOR, WIND_WITH_FACTOR
        return max(lo, min(hi, 1.0 + alignment * (hi - 1.0)
                           if alignment >= 0 else 1.0 + alignment
                           * (1.0 - lo)))

    # -------------------------------------------------------- defenestration
    def nearest_pane(self, pos: Vec3) -> Optional[WindowPane]:
        """Closest pane (open ones first) to a position, XZ distance."""
        def dist(pane: WindowPane) -> float:
            return math.hypot(float(pos.x) - float(pane.entity.x),
                              float(pos.z) - float(pane.entity.z))
        open_panes = [p for p in self.panes if not p.broken]
        pool = open_panes if open_panes else self.panes
        return min(pool, key=dist) if pool else None

    def throw_enemy_out(self, enemy, stunt=None) -> dict:
        """Throw an enemy out of the tower through the nearest pane.

        Breaks the pane (if still whole), moves the enemy's entity out
        past the glass line and marks it defeated, and — when a
        StuntManager is given — registers DEFENESTRATION (500 PTS) so
        the move flows through the real combo/rating math. Returns
        {"pane", "stunt_points"} (stunt_points None without a manager).
        """
        pane = self.nearest_pane(enemy.position)
        if pane is None:
            raise RuntimeError("Penthouse has no window panes")
        pane.break_pane()
        out = pane.outward
        enemy.entity.position = Vec3(
            float(pane.entity.x) + out.x * 4.0, 0.45,
            float(pane.entity.z) + out.z * 4.0)
        enemy.entity.rotation_z = 82
        if hasattr(enemy, "alive"):
            enemy.alive = False
        if hasattr(enemy, "state"):
            enemy.state = "defenestrated"
        added = None
        if stunt is not None:
            added, _mult = stunt.register("defenestration")
        logger.info("Enemy thrown out through %s (stunt +%s)",
                    pane.name, added)
        return {"pane": pane.name, "stunt_points": added}

    # ------------------------------------------------------------------ tick
    def tick(self, dt: float) -> None:
        """Advance cover flashes + the wind-blown dust over the deck."""
        if dt <= 0:
            return
        for cover in self.covers:
            cover.tick(dt)
        for mote in self._dust:
            mote.position += WIND_VECTOR * dt
            if mote.x > ROOM_MAX_X or mote.z < ROOF_DECK_MIN_Z - 2:
                mote.position = Vec3(-ROOM_MAX_X + 1.0, ROOF_Y + 0.8,
                                     9.0 + (float(mote.y) * 7 % 5) * 1.6)
