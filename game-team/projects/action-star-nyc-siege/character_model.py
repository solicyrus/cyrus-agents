"""ActionStarModel — the protagonist's visual body (code-built v1).

WHAT THIS IS, HONESTLY: a stylized humanoid assembled from Ursina
primitive cubes in code — dark tactical outfit, skin-tone head,
near-black "fingerless glove" hands, a pistol in the right hand and a
visible holster box strapped to EACH thigh (the approved look: John
Wick / Mission: Impossible inspirations, Cyrus 2026-10-27). It is NOT
a rigged or skeletal asset and has no mocap: the seven poses below are
engineered part transforms (pivot rotations / offsets) switched by
:meth:`ActionStarModel.set_pose`, with a procedural leg/arm swing
while running. The docstring, the GDD and the QA report all describe
it exactly this way — a code-built stylized model v1.

Structure (all parts hang under ``rig``, a child of ``root``):

    root            physics anchor — the PlayerController's entity.
                    The controller moves/rotates THIS (rotation_y =
                    aim yaw); poses never touch it, so collision and
                    facing are exactly the pre-model behaviour.
    rig             pose group: slide drop, wall-run bank, dodge lean
                    are applied here.
    torso (group)   chest + head + arms, so a melee twist carries the
                    whole upper body.
    arm_l / arm_r   shoulder pivots (upper arm + hand [+ gun on R]).
    leg_l / leg_r   hip pivots (thigh + boot + thigh holster).

Pose states (set_pose): IDLE, RUN, AIM, SLIDE, MELEE, WALLRUN, DODGE.
AIM uses the live aim pitch (set_aim_pitch), WALLRUN banks toward the
wall side (set_wallrun_side, +1 = wall on the facing-right), RUN swings
limbs in update(). Every pose application first resets every
pose-affected transform, so a pose snapshot is deterministic — the QA
test (test_character.py) measures exactly that.
"""

from __future__ import annotations

import logging
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ursina import Entity, Vec3, color  # noqa: E402

from level1.lobby_level import LIT  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Palette — the approved look: near-black tactical, gold-free, skin head,
# darker-still hands (fingerless gloves read as black blocks at this scale).
# ---------------------------------------------------------------------------
COL_TACTICAL = color.rgb(24, 26, 34)      # torso / sleeves
COL_TROUSERS = color.rgb(17, 18, 23)      # legs
COL_VEST = color.rgb(40, 44, 56)          # chest plate
COL_SKIN = color.rgb(216, 166, 122)       # head
COL_HAIR = color.rgb(28, 22, 18)
COL_GLOVE = color.rgb(10, 10, 12)         # fingerless-glove hands
COL_HOLSTER = color.rgb(12, 12, 15)       # thigh holsters
COL_GUN = color.rgb(16, 16, 20)
COL_BOOT = color.rgb(14, 14, 17)
COL_BELT = color.rgb(52, 44, 30)

POSES = ("IDLE", "RUN", "AIM", "SLIDE", "MELEE", "WALLRUN", "DODGE")


class ActionStarModel:
    """The Action Star's body. Construct after the Ursina app exists.

    ``root`` is handed to the PlayerController as its entity; the
    controller owns root.position / root.rotation_y, this class owns
    everything below it.
    """

    def __init__(self, spawn: Vec3 = Vec3(0, 0.9, 0)) -> None:
        self.root = Entity(model=None, position=spawn)
        self.rig = Entity(parent=self.root, model=None)
        self.parts: dict = {"root": self.root, "rig": self.rig}
        self._build_torso()
        self._build_arms()
        self._build_legs()
        self.pose: str = ""
        self._aim_pitch: float = 0.0
        self._wallrun_side: int = 1
        self._run_phase: float = 0.0
        self.set_pose("IDLE")
        logger.info("ActionStarModel built: %d named parts",
                    len(self.parts))

    # ------------------------------------------------------------- build
    def _box(self, name: str, parent: Entity, pos, scale, col) -> Entity:
        ent = Entity(parent=parent, model="cube", position=pos,
                     scale=scale, color=col, shader=LIT)
        self.parts[name] = ent
        return ent

    def _build_torso(self) -> None:
        torso = Entity(parent=self.rig, model=None, position=(0, 0.02, 0))
        self.parts["torso"] = torso
        self.torso = torso
        self._box("chest", torso, (0, 0.26, 0), (0.62, 0.62, 0.38),
                  COL_TACTICAL)
        self._box("chest_plate", torso, (0, 0.30, 0.215),
                  (0.46, 0.40, 0.05), COL_VEST)
        self._box("belt", torso, (0, -0.10, 0), (0.56, 0.12, 0.36),
                  COL_BELT)
        head_grp = Entity(parent=torso, model=None, position=(0, 0.62, 0))
        self.parts["head_grp"] = head_grp
        self._box("head", head_grp, (0, 0.17, 0), (0.40, 0.42, 0.40),
                  COL_SKIN)
        self._box("hair", head_grp, (0, 0.40, -0.02), (0.44, 0.13, 0.44),
                  COL_HAIR)

    def _build_arms(self) -> None:
        self.arm_l = Entity(parent=self.torso, model=None,
                            position=(-0.42, 0.50, 0))
        self.arm_r = Entity(parent=self.torso, model=None,
                            position=(0.42, 0.50, 0))
        self.parts["arm_l"] = self.arm_l
        self.parts["arm_r"] = self.arm_r
        for side, pivot in (("l", self.arm_l), ("r", self.arm_r)):
            self._box(f"upperarm_{side}", pivot, (0, -0.20, 0),
                      (0.15, 0.42, 0.15), COL_TACTICAL)
            # Near-black hand block: the fingerless glove.
            self._box(f"hand_{side}", pivot, (0, -0.48, 0),
                      (0.14, 0.15, 0.14), COL_GLOVE)
        # Pistol in the right (gun) hand.
        self._box("gun", self.arm_r, (0, -0.52, 0.16),
                  (0.08, 0.11, 0.46), COL_GUN)

    def _build_legs(self) -> None:
        self.leg_l = Entity(parent=self.rig, model=None,
                            position=(-0.17, -0.24, 0))
        self.leg_r = Entity(parent=self.rig, model=None,
                            position=(0.17, -0.24, 0))
        self.parts["leg_l"] = self.leg_l
        self.parts["leg_r"] = self.leg_r
        for side, pivot, outward in (("l", self.leg_l, -1),
                                     ("r", self.leg_r, 1)):
            self._box(f"thigh_{side}", pivot, (0, -0.20, 0),
                      (0.20, 0.44, 0.22), COL_TROUSERS)
            self._box(f"boot_{side}", pivot, (0, -0.55, 0.03),
                      (0.21, 0.13, 0.32), COL_BOOT)
            # Dual thigh holsters: a strapped box on the OUTER thigh
            # plus the grip of the holstered pistol above it.
            self._box(f"holster_{side}", pivot,
                      (outward * 0.17, -0.20, 0),
                      (0.10, 0.36, 0.15), COL_HOLSTER)
            self._box(f"holster_grip_{side}", pivot,
                      (outward * 0.17, 0.03, -0.02),
                      (0.09, 0.11, 0.09), COL_GUN)

    # -------------------------------------------------------------- poses
    def set_aim_pitch(self, pitch_deg: float) -> None:
        """Live aim pitch (degrees); the AIM/SLIDE gun arm tracks it."""
        self._aim_pitch = float(pitch_deg)
        if self.pose in ("AIM", "SLIDE"):
            self.arm_r.rotation_x = -(90.0 + self._aim_pitch)

    def set_wallrun_side(self, side: int) -> None:
        """+1 = wall on the player's facing-right, -1 = on the left.
        The WALLRUN bank leans the body TOWARD that side."""
        self._wallrun_side = 1 if side >= 0 else -1
        if self.pose == "WALLRUN":
            self._apply_wallrun()

    def _reset_pose_transforms(self) -> None:
        self.rig.position = Vec3(0, 0, 0)
        self.rig.rotation = Vec3(0, 0, 0)
        self.torso.rotation = Vec3(0, 0, 0)
        for pivot in (self.arm_l, self.arm_r, self.leg_l, self.leg_r):
            pivot.rotation = Vec3(0, 0, 0)
        self.arm_l.rotation_z = 6.0      # relaxed rest angle
        self.arm_r.rotation_z = -6.0

    def set_pose(self, state: str) -> None:
        state = str(state).upper()
        if state not in POSES:
            raise ValueError(f"unknown pose {state!r}; poses: {POSES}")
        self.pose = state
        self._reset_pose_transforms()
        if state == "IDLE":
            pass
        elif state == "RUN":
            self.rig.rotation_x = 6.0            # forward lean
            self.leg_l.rotation_x = 24.0         # static stride snapshot;
            self.leg_r.rotation_x = -24.0        # update() animates it
            self.arm_l.rotation_x = -18.0
            self.arm_r.rotation_x = 14.0
        elif state == "AIM":
            self.torso.rotation_y = -8.0         # bladed stance
            self.arm_r.rotation_x = -(90.0 + self._aim_pitch)
            self.arm_l.rotation_x = -35.0        # support hand forward
        elif state == "SLIDE":
            self.rig.position = Vec3(0, -0.52, 0)   # body drops low
            self.rig.rotation_x = -32.0             # pitched back, low
            self.leg_l.rotation_x = -75.0           # legs extended ahead
            self.leg_r.rotation_x = -68.0
            self.arm_r.rotation_x = -(90.0 + self._aim_pitch)
            self.arm_l.rotation_x = 30.0            # trailing hand
        elif state == "MELEE":
            self.torso.rotation_y = 28.0            # strike twist
            self.rig.rotation_x = 8.0
            self.arm_r.rotation_x = -150.0          # strike arm overhead
            self.arm_l.rotation_x = 25.0
        elif state == "WALLRUN":
            self._apply_wallrun()
        elif state == "DODGE":
            self.rig.rotation_z = -14.0            # cinematic lean
            self.rig.position = Vec3(0, -0.10, 0)
            self.arm_l.rotation_z = -28.0           # arms out for balance
            self.arm_r.rotation_z = 28.0
        logger.debug("ActionStar pose -> %s", state)

    def _apply_wallrun(self) -> None:
        side = self._wallrun_side
        # Bank TOWARD the wall: the body's top tips to the wall side.
        self.rig.rotation_z = -18.0 * side
        wall_leg = self.leg_r if side > 0 else self.leg_l
        free_leg = self.leg_l if side > 0 else self.leg_r
        wall_leg.rotation_x = -50.0      # wall-side leg pressed to the wall
        free_leg.rotation_x = -12.0
        self.arm_r.rotation_x = -(90.0 + self._aim_pitch)   # gun stays up

    # -------------------------------------------------------------- frame
    def update(self, dt: float, speed_factor: float = 0.0) -> None:
        """Per-frame animation. Only RUN is continuous (limb swing);
        ``speed_factor`` is the player's ground speed (units/s)."""
        if self.pose != "RUN" or dt <= 0:
            return
        self._run_phase += dt * (4.0 + 1.1 * max(0.0, speed_factor))
        swing = math.sin(self._run_phase) * 26.0
        self.leg_l.rotation_x = swing
        self.leg_r.rotation_x = -swing
        self.arm_l.rotation_x = -swing * 0.7
        self.arm_r.rotation_x = swing * 0.7
