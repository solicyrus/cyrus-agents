"""LobbyLevel — the 3D tower lobby of Level 1 (Action Star: NYC Siege 3D).

Builds the full greybox scene for the ground floor of the NYC tower:

  * interior shell: floor, ceiling, four walls (interior 44 x 30 units);
  * six marble columns in two rows;
  * a glass entrance across the south wall (transparent panels + marble
    door posts);
  * a reception desk and planters / console desks placed as cover;
  * the main ELEVATOR on the north wall — doors, gold trim, glow sign —
    with the level's goal zone on the floor in front of it;
  * cinematic lighting: a warm directional key light, a low cool ambient,
    a warm point light over the lobby centre and a cool point light at
    the elevator (all materials use Ursina's basic lighting shader, so
    the lights genuinely shape the scene; shadows are off — see
    FEASIBILITY.md on software rendering).

Collision: every solid registers in one shared :class:`CollisionWorld`
(AABB boxes). The player controller and the guard AI both move and shoot
through THIS world — there is no second, divergent collision model.
Movement collision is a circle-vs-AABB resolution in the XZ plane
(characters stay on the lobby floor); ray queries (hitscan, line of
sight, bullet impact) use the full 3D boxes.

The third-person camera rig also lives here (:class:`ThirdPersonCamera`)
and is exposed for the player controller / session to drive.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ursina import AmbientLight, DirectionalLight, Entity, PointLight, Vec3, camera, color
from ursina.shaders import basic_lighting_shader

logger = logging.getLogger(__name__)

LIT = basic_lighting_shader

# ---------------------------------------------------------------------------
# Room dimensions (interior faces). Characters move in XZ inside these.
# ---------------------------------------------------------------------------
ROOM_MIN_X, ROOM_MAX_X = -22.0, 22.0
ROOM_MIN_Z, ROOM_MAX_Z = -15.0, 15.0
WALL_HEIGHT = 6.0
WALL_THICKNESS = 1.0

# Palette — warm marble lobby with cool glass/steel accents.
COL_FLOOR = color.rgb32(96, 88, 78)
COL_WALL = color.rgb32(150, 138, 120)
COL_MARBLE = color.rgb32(196, 188, 172)
COL_DESK = color.rgb32(84, 62, 44)
COL_PLANTER = color.rgb32(52, 84, 52)
COL_GLASS = color.rgba32(140, 190, 225, 90)
COL_STEEL = color.rgb32(120, 128, 140)
COL_GOLD = color.rgb32(198, 158, 60)
COL_RUG = color.rgb32(96, 30, 36)
COL_CEILING = color.rgb32(60, 58, 62)
COL_LIGHT_PANEL = color.rgb32(255, 236, 190)


def forward_from_yaw(yaw_deg: float) -> Vec3:
    """Unit forward vector for a yaw in degrees (yaw 0 -> +Z / north)."""
    rad = math.radians(yaw_deg)
    return Vec3(math.sin(rad), 0.0, math.cos(rad))


def yaw_towards(dx: float, dz: float) -> float:
    """Yaw in degrees whose forward points along (dx, dz)."""
    return math.degrees(math.atan2(dx, dz))


# ---------------------------------------------------------------------------
# Collision world
# ---------------------------------------------------------------------------
@dataclass
class Solid:
    """One axis-aligned solid box. (cx, cz) centre, (sx, sy, sz) size,
    base y = y0 (0 for everything standing on the lobby floor)."""

    name: str
    cx: float
    cz: float
    sx: float
    sy: float
    sz: float
    y0: float = 0.0

    @property
    def min_x(self) -> float:
        return self.cx - self.sx / 2.0

    @property
    def max_x(self) -> float:
        return self.cx + self.sx / 2.0

    @property
    def min_z(self) -> float:
        return self.cz - self.sz / 2.0

    @property
    def max_z(self) -> float:
        return self.cz + self.sz / 2.0

    @property
    def max_y(self) -> float:
        return self.y0 + self.sy


class CollisionWorld:
    """Shared AABB collision set for movement, rays and point queries."""

    def __init__(self) -> None:
        self.solids: List[Solid] = []

    def add(self, solid: Solid) -> Solid:
        self.solids.append(solid)
        return solid

    # ------------------------------------------------------------ movement
    def _circle_overlaps(self, x: float, z: float, radius: float) -> bool:
        """True if a circle at (x, z) penetrates any solid's XZ footprint."""
        r2 = radius * radius
        for s in self.solids:
            nx = max(s.min_x, min(x, s.max_x))
            nz = max(s.min_z, min(z, s.max_z))
            dx = x - nx
            dz = z - nz
            if dx * dx + dz * dz < r2:
                return True
        return False

    def circle_gap(self, x: float, z: float, radius: float) -> float:
        """Smallest clearance between the circle and any solid footprint
        (negative when penetrating). Diagnostic / QA evidence helper."""
        best = float("inf")
        for s in self.solids:
            nx = max(s.min_x, min(x, s.max_x))
            nz = max(s.min_z, min(z, s.max_z))
            gap = math.hypot(x - nx, z - nz) - radius
            if gap < best:
                best = gap
        return best

    def move(self, pos: Vec3, radius: float, delta: Vec3) -> Vec3:
        """Move a character circle by ``delta`` (XZ), axis-separated so a
        blocked axis slides along the obstacle instead of sticking.
        Returns the new position (y unchanged)."""
        x, z = float(pos.x), float(pos.z)
        cand_x = x + float(delta.x)
        if not self._circle_overlaps(cand_x, z, radius):
            x = cand_x
        cand_z = z + float(delta.z)
        if not self._circle_overlaps(x, cand_z, radius):
            z = cand_z
        return Vec3(x, float(pos.y), z)

    # ---------------------------------------------------------------- rays
    def ray_hit(self, origin: Vec3, direction: Vec3,
                max_dist: float) -> Optional[float]:
        """Nearest ray-vs-AABB distance along ``direction`` (must be
        normalised) up to ``max_dist``, or None when nothing is hit.
        Used for hitscan shots, guard line-of-sight and bullet impact."""
        hit = self.ray_hit_solid(origin, direction, max_dist)
        return hit[0] if hit is not None else None

    def ray_hit_solid(self, origin: Vec3, direction: Vec3,
                      max_dist: float) -> Optional[Tuple[float, str]]:
        """Like :meth:`ray_hit` but returns ``(distance, solid_name)`` —
        QA evidence for exactly WHICH cover a shot impacted."""
        best: Optional[Tuple[float, str]] = None
        o = (float(origin.x), float(origin.y), float(origin.z))
        d = (float(direction.x), float(direction.y), float(direction.z))
        for s in self.solids:
            lo = (s.min_x, s.y0, s.min_z)
            hi = (s.max_x, s.max_y, s.max_z)
            t_min, t_max = 0.0, max_dist
            blocked = False
            for axis in range(3):
                if abs(d[axis]) < 1e-9:
                    if o[axis] < lo[axis] or o[axis] > hi[axis]:
                        blocked = True
                        break
                else:
                    inv = 1.0 / d[axis]
                    t1 = (lo[axis] - o[axis]) * inv
                    t2 = (hi[axis] - o[axis]) * inv
                    if t1 > t2:
                        t1, t2 = t2, t1
                    t_min = max(t_min, t1)
                    t_max = min(t_max, t2)
                    if t_min > t_max:
                        blocked = True
                        break
            if not blocked and (best is None or t_min < best[0]):
                best = (t_min, s.name)
        return best

    def line_of_sight(self, a: Vec3, b: Vec3) -> bool:
        """True when the straight segment a->b is not blocked by a solid."""
        delta = b - a
        dist = delta.length()
        if dist < 1e-6:
            return True
        hit = self.ray_hit(a, delta / dist, dist)
        return hit is None or hit >= dist - 0.05

    def point_blocked(self, p: Vec3) -> bool:
        """True when point p sits inside any solid's 3D box."""
        for s in self.solids:
            if (s.min_x <= p.x <= s.max_x and s.y0 <= p.y <= s.max_y
                    and s.min_z <= p.z <= s.max_z):
                return True
        return False


# ---------------------------------------------------------------------------
# Third-person camera rig
# ---------------------------------------------------------------------------
class ThirdPersonCamera:
    """Over-the-shoulder (OTS) follow camera.

    The camera sits behind/above the player AND offset to the player's
    RIGHT shoulder (``shoulder`` units along the facing-right vector),
    looking ahead along a line that carries the same shoulder offset —
    so the player reads left-of-frame and the crosshair line (the
    camera's forward) is the honest aim line. The session drives it
    with the player's position and aim yaw/pitch; the controller reads
    :meth:`aim_ray` and resolves its hitscan from the camera aim
    (crosshair), never from the character's feet.

    The camera position is clamped inside the room so walls never
    swallow it in this interior level (greybox-grade camera
    collision)."""

    # Wall-run camera roll (Cyrus's Unity reference): the frame tilts
    # toward the wall side — left wall -15 deg, right wall +15 deg —
    # lerped smoothly in and out.
    WALLRUN_ROLL_DEG = 15.0
    ROLL_LERP_RATE = 7.0

    def __init__(self, distance: float = 6.5, height: float = 2.4,
                 look_ahead: float = 4.0, shoulder: float = 1.15) -> None:
        self.distance = float(distance)
        self.height = float(height)
        self.look_ahead = float(look_ahead)
        self.shoulder = float(shoulder)
        self.roll: float = 0.0        # current camera roll (degrees)
        self._aim_origin: Optional[Vec3] = None
        self._aim_direction: Optional[Vec3] = None

    @staticmethod
    def right_from_yaw(yaw_deg: float) -> Vec3:
        """Unit right vector for a facing yaw (matches main.py)."""
        fwd = forward_from_yaw(yaw_deg)
        return Vec3(fwd.z, 0.0, -fwd.x)

    def update(self, target_pos: Vec3, yaw_deg: float,
               pitch_deg: float = 0.0, wall_side: int = 0,
               dt: float = 1.0 / 60.0) -> None:
        """``wall_side``: +1 when the player is wall-running with the
        wall on their facing-right, -1 on their facing-left, 0 when
        not wall-running — drives the camera roll toward
        +/-WALLRUN_ROLL_DEG or back to level."""
        fwd = forward_from_yaw(yaw_deg)
        right = Vec3(fwd.z, 0.0, -fwd.x)
        desired = Vec3(
            target_pos.x - fwd.x * self.distance + right.x * self.shoulder,
            target_pos.y + self.height + pitch_deg * 0.04,
            target_pos.z - fwd.z * self.distance + right.z * self.shoulder,
        )
        camera.position = Vec3(
            max(ROOM_MIN_X + 0.6, min(ROOM_MAX_X - 0.6, desired.x)),
            max(1.4, min(WALL_HEIGHT - 0.4, desired.y)),
            max(ROOM_MIN_Z + 0.6, min(ROOM_MAX_Z - 0.6, desired.z)),
        )
        look = Vec3(
            target_pos.x + fwd.x * self.look_ahead + right.x * self.shoulder,
            target_pos.y + 0.7,
            target_pos.z + fwd.z * self.look_ahead + right.z * self.shoulder,
        )
        camera.look_at(look)
        # Wall-run roll: lerp toward the wall side's tilt (or level),
        # applied on top of the look_at orientation.
        target_roll = self.WALLRUN_ROLL_DEG * (1 if wall_side > 0
                                               else -1 if wall_side < 0
                                               else 0)
        self.roll += (target_roll - self.roll) \
            * min(1.0, max(0.0, dt) * self.ROLL_LERP_RATE)
        if abs(self.roll) > 0.001:
            camera.rotation_z = self.roll
        # The aim ray through the crosshair: from the (clamped) camera
        # position along its true forward after look_at.
        self._aim_origin = Vec3(camera.position.x, camera.position.y,
                                camera.position.z)
        delta = look - camera.position
        self._aim_direction = delta.normalized() if delta.length() > 1e-6 \
            else fwd

    def aim_ray(self) -> Optional[Tuple[Vec3, Vec3]]:
        """(origin, direction) of the crosshair line, from the most
        recent update(); None before the first update (callers fall
        back to the character's own aim for that first frame)."""
        if self._aim_origin is None or self._aim_direction is None:
            return None
        return self._aim_origin, self._aim_direction


# ---------------------------------------------------------------------------
# The lobby itself
# ---------------------------------------------------------------------------
class LobbyLevel:
    """Builds the lobby scene and exposes its collision world + goal."""

    # Goal zone (floor rectangle in front of the elevator doors).
    GOAL_ZONE: Tuple[float, float, float, float] = (-3.0, 3.0, 12.6, 14.3)

    def __init__(self) -> None:
        self.world = CollisionWorld()
        self.entities: List[Entity] = []
        self.camera_rig = ThirdPersonCamera()
        self._build_shell()
        self._build_columns()
        self._build_entrance()
        self._build_furniture()
        self._build_elevator()
        self._build_lights()
        logger.info("Lobby built: %d solids registered",
                    len(self.world.solids))

    # ------------------------------------------------------------- helpers
    def _solid(self, name: str, cx: float, cz: float, size: Tuple[float, float, float],
               solid_color, y_base: float = 0.0) -> Entity:
        """Create a visual box AND register it as a collision solid."""
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
        """A purely visual box (no collision registration)."""
        ent = Entity(model="cube", scale=size, position=(cx, cy, cz),
                     color=visual_color, shader=LIT if lit else None)
        self.entities.append(ent)
        return ent

    # ------------------------------------------------------------ geometry
    def _build_shell(self) -> None:
        # Floor + rug + ceiling (visual only; movement is planar).
        self._visual(0, -0.25, 0, (48, 0.5, 36), COL_FLOOR)
        self._visual(0, 0.03, -2, (16, 0.06, 22), COL_RUG)
        self._visual(0, WALL_HEIGHT + 0.25, 0, (48, 0.5, 36), COL_CEILING)
        # Ceiling light panels (bright, unlit so they read as emitters).
        for x in (-11, 0, 11):
            for z in (-8, 3):
                self._visual(x, WALL_HEIGHT - 0.06, z, (5.5, 0.12, 2.6),
                             COL_LIGHT_PANEL, lit=False)
        # Walls (solids). North wall is continuous; the elevator doors sit
        # flush on its interior face and the goal zone lies in front.
        t = WALL_THICKNESS
        self._solid("wall_north", 0, ROOM_MAX_Z + t / 2, (48, WALL_HEIGHT, t), COL_WALL)
        self._solid("wall_east", ROOM_MAX_X + t / 2, 0, (t, WALL_HEIGHT, 36), COL_WALL)
        self._solid("wall_west", -ROOM_MAX_X - t / 2, 0, (t, WALL_HEIGHT, 36), COL_WALL)
        # South wall: two marble segments flanking the glass entrance.
        self._solid("wall_south_west", -14.5, -ROOM_MAX_Z - t / 2,
                    (17, WALL_HEIGHT, t), COL_WALL)
        self._solid("wall_south_east", 14.5, -ROOM_MAX_Z - t / 2,
                    (17, WALL_HEIGHT, t), COL_WALL)

    def _build_columns(self) -> None:
        """Six marble columns, two rows — the lobby's main hard cover."""
        for x in (-8.0, 8.0):
            for z in (-8.0, 0.0, 8.0):
                self._solid(f"column_{x:+.0f}_{z:+.0f}", x, z,
                            (1.6, WALL_HEIGHT, 1.6), COL_MARBLE)
                # Gold trim ring near the top of each column (visual).
                self._visual(x, WALL_HEIGHT - 0.7, z, (1.75, 0.18, 1.75),
                             COL_GOLD)

    def _build_entrance(self) -> None:
        """Glass entrance on the south wall: transparent panels + posts."""
        z = -ROOM_MAX_Z - WALL_THICKNESS / 2
        for x in (-4.5, -1.5, 1.5, 4.5):
            glass = self._solid(f"glass_{x:+.1f}", x, z,
                                (2.9, 4.6, 0.35), COL_GLASS)
            glass.alpha = 0.35
        # Marble door posts at both ends of the glass run.
        self._solid("door_post_west", -6.2, z, (0.5, WALL_HEIGHT, 0.8), COL_MARBLE)
        self._solid("door_post_east", 6.2, z, (0.5, WALL_HEIGHT, 0.8), COL_MARBLE)
        # Marble lintel above the glass.
        self._visual(0, 5.3, z, (13, 1.4, 0.9), COL_MARBLE)

    def _build_furniture(self) -> None:
        """Reception desk + cover objects."""
        # Reception desk, south-centre (the first cover a player meets).
        self._solid("reception_desk", 0, -7.0, (7.0, 1.15, 2.2), COL_DESK)
        self._visual(0, 1.22, -7.0, (7.3, 0.14, 2.5), COL_GOLD)
        # Planters (green cover blocks) mid-lobby, both flanks.
        for x in (-15.0, 15.0):
            for z in (-4.0, 6.0):
                self._solid(f"planter_{x:+.0f}_{z:+.0f}", x, z,
                            (3.0, 1.0, 1.6), COL_PLANTER)
        # Console desks against the side walls, north half.
        self._solid("console_west", -19.5, 10.0, (4.0, 1.1, 1.8), COL_DESK)
        self._solid("console_east", 19.5, 10.0, (4.0, 1.1, 1.8), COL_DESK)

    def _build_elevator(self) -> None:
        """The main elevator on the north wall — the level goal."""
        z_face = ROOM_MAX_Z - 0.06
        # Recessed dark shaft panel behind the doors (visual).
        self._visual(0, 2.6, z_face + 0.25, (7.4, 5.2, 0.3), COL_STEEL)
        # Two steel doors, flush with the wall face (the wall solid behind
        # them is what stops the player; the goal triggers before contact).
        self._visual(-0.85, 2.1, z_face, (1.6, 4.2, 0.18), COL_STEEL)
        self._visual(0.85, 2.1, z_face, (1.6, 4.2, 0.18), COL_STEEL)
        # Gold frame + header sign panel (bright, reads as lit signage).
        self._visual(0, 4.55, z_face, (4.4, 0.5, 0.2), COL_GOLD)
        self._visual(0, 5.25, z_face, (3.2, 0.7, 0.15), COL_LIGHT_PANEL,
                     lit=False)
        # Goal-zone floor marking in front of the doors.
        gx0, gx1, gz0, gz1 = self.GOAL_ZONE
        self._visual((gx0 + gx1) / 2, 0.04, (gz0 + gz1) / 2,
                     (gx1 - gx0, 0.08, gz1 - gz0), COL_GOLD)

    def _build_lights(self) -> None:
        """Cinematic rig: warm key, cool fill, two practical points."""
        key = DirectionalLight(shadows=False)
        key.rotation = (48, -32, 0)
        key.color = color.rgb32(255, 216, 175)
        fill = AmbientLight()
        fill.color = color.rgb32(72, 82, 104)
        warm = PointLight()
        warm.position = (0, 5.0, -2)
        warm.color = color.rgb32(255, 190, 130)
        warm.range = 34
        cool = PointLight()
        cool.position = (0, 4.4, 12.5)
        cool.color = color.rgb32(140, 180, 255)
        cool.range = 22
        self.entities.extend([key, fill, warm, cool])

    # -------------------------------------------------------------- queries
    def point_in_goal(self, pos: Vec3) -> bool:
        gx0, gx1, gz0, gz1 = self.GOAL_ZONE
        return gx0 <= pos.x <= gx1 and gz0 <= pos.z <= gz1
