"""DestructibleCover — cover that does not last (Stage 3, both floors).

Cyrus's Stage-3 gameplay rule: wooden desks and plaster columns shatter
under fire, so the player (and the enemies) cannot camp behind one point
forever. A DestructibleCover is a normal CollisionWorld solid plus a
visual box, with hit points on top:

  * ``take_damage(dmg)`` accumulates bullet damage; hits flash the box.
  * When HP reaches zero the cover BREAKS: the solid is REMOVED from the
    shared CollisionWorld (bullets and movement genuinely pass through
    from that moment — this is a state change in the one collision
    model, not a visual trick), the box collapses to a low rubble slab
    and a few debris chunks are scattered.

The class is engine-real but session-agnostic: the shooter (player
controller / test) routes cover hits into ``take_damage`` exactly the
way level1 routes guard hits.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ursina import Entity, Vec3, color  # noqa: E402

from level1.lobby_level import LIT, CollisionWorld, Solid  # noqa: E402

logger = logging.getLogger(__name__)

COL_RUBBLE = color.rgb(105, 96, 86)


class DestructibleCover:
    """One breakable cover object registered in a CollisionWorld."""

    def __init__(self, world: CollisionWorld, name: str, cx: float, cz: float,
                 size: tuple, cover_color, hp: float,
                 y_base: float = 0.0) -> None:
        sx, sy, sz = size
        self.world = world
        self.name = name
        self.max_hp = float(hp)
        self.hp = float(hp)
        self.broken = False
        self._base_color = cover_color
        self._flash_ttl = 0.0
        self.entity = Entity(model="cube", scale=(sx, sy, sz),
                             position=(cx, y_base + sy / 2.0, cz),
                             color=cover_color, shader=LIT)
        self.solid = world.add(Solid(name=name, cx=cx, cz=cz, sx=sx, sy=sy,
                                     sz=sz, y0=y_base))
        self.debris: List[Entity] = []
        logger.info("Destructible cover %s placed (HP %.0f)", name, self.hp)

    # ------------------------------------------------------------------ API
    @property
    def position(self) -> Vec3:
        return self.entity.position

    def take_damage(self, dmg: float) -> bool:
        """Apply bullet damage. Returns True only on the breaking hit."""
        if self.broken or dmg <= 0:
            return False
        self.hp = max(0.0, self.hp - float(dmg))
        self._flash_ttl = 0.08
        logger.info("Cover %s took %.0f damage -> HP %.0f",
                    self.name, dmg, self.hp)
        if self.hp <= 0.0:
            self._break()
            return True
        return False

    def tick(self, dt: float) -> None:
        """Restore the base colour after a hit flash."""
        if self._flash_ttl > 0:
            self._flash_ttl -= dt
            if self._flash_ttl <= 0 and not self.broken:
                self.entity.color = self._base_color

    # -------------------------------------------------------------- internals
    def _break(self) -> None:
        self.broken = True
        # State change in the ONE collision model: the solid leaves the
        # world, so rays and movement pass through the footprint now.
        if self.solid in self.world.solids:
            self.world.solids.remove(self.solid)
        # Collapse the box to a rubble slab (still visible, no collision).
        cx, cz = float(self.entity.x), float(self.entity.z)
        self.entity.scale = (self.entity.scale_x, 0.28, self.entity.scale_z)
        self.entity.y = 0.14
        self.entity.color = COL_RUBBLE
        for i, (ox, oz) in enumerate(((-0.7, 0.4), (0.6, -0.5), (0.1, 0.8))):
            chunk = Entity(model="cube", scale=(0.42, 0.3, 0.42),
                           position=(cx + ox, 0.15, cz + oz),
                           rotation_y=i * 37.0, color=COL_RUBBLE,
                           shader=LIT)
            self.debris.append(chunk)
        logger.info("Cover %s DESTROYED — solid removed from the world",
                    self.name)
