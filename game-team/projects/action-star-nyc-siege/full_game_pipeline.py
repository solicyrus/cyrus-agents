"""full_game_pipeline — Action Star: NYC Siege 3D as ONE run of three
floors: Lobby -> (elevator) -> Data Center -> (elevator) -> Penthouse.

Cyrus's integration order (2026-10-27, after Stage 3's 30/30 QA pass):
chain the studio's three proven floors into a single game with
persistent state, elevator transitions, and one Final Take Rating.

CHAIN RULES (implemented here + pipeline_state.py; documented in both):

1. ONE StuntManager across all three floors (pipeline_state.RunState):
   score, combo multiplier, recent-action chain and raw base total are
   NEVER reset between floors. Each floor gets a fresh PlayerController
   (it is bound to its floor's CollisionWorld) but all controllers are
   wired to the SAME manager, so a hit on any floor resets the shared
   combo, exactly per the StuntManager rules.

2. TIME BANKING: each floor's TimerManager cap = base target
   (Lobby 90 s / Data Center 75 s / Penthouse 105 s) + the seconds
   banked from the previous floor (banked = max(0, previous effective
   cap - previous actual)). See pipeline_state.RunState.

3. HEAL BY RANK (v1 table, Cyrus's "heal based on rank"): at each
   floor's end the floor's own take is rated (floor S_time + the stunt
   base gained on that floor, via logic/take_rating.evaluate); the
   player heals S -> 100% HP, A -> +60, B -> +40, C -> +25 (cap 100).
   A floor rated F — or lost outright — is a failed take: the chain
   stops for a Re-take, no advance, no heal, no banking.

4. FINAL CARD: S_total = SUM(floor S_time) + (total raw stunt base x
   final combo multiplier), computed by logic/take_rating.evaluate on
   the shared manager's totals. The result is handed to phase4's
   VictoryScreen (show_result(result, run_record)) when one is
   supplied, and is always available as pipeline.final_record in the
   same shape (see SEAMS below).

5. SAVE WIRING (integration note, 2026-10-27): at each floor's end,
   after its take is rated, the pipeline calls
   SaveManager.save_stage_result(level_num, floor S_total, floor
   actual time, floor rank) through pipeline_state.SaveBridge
   (Lobby=1, Data Center=2, Penthouse=3). The pipeline also accepts a
   starting floor (level-select entry): starting at floor N > 1 begins
   there with a FRESH RunState (fresh StuntManager/TimerManager, full
   HP, no bank) while per-floor saves still fire. When the save system
   is present, a locked floor refuses to start (SaveBridge.is_unlocked).

FLOOR ASSEMBLY: each FloorSession is assembled from the studio's real
modules exactly the way level1/main.GameSession assembles the Lobby —
same tick order, same HUD pushes — parameterized by floor:
  * Floor 1: level1 LobbyLevel + 3 Guards; win = elevator goal zone.
  * Floor 2: stage3 DataCenterLevel + Enforcer + Marksman;
    win = the floor's elevator zone (see NOTE in _arm_floor).
  * Floor 3: stage3 PenthouseLevel + Marksman + the Syndicate Boss
    (stage3 BossHealthBar on screen); win = boss defeated.
Lose on every floor: HP reaches zero, or the effective target passes.
The session layer also routes hitscan cover hits into the floors'
interactive objects (server racks, destructible cover, window panes)
and reports gunfire to the Data Center's sprinkler system — the
routing stage3's level docstrings assign to "the session".

ENEMY TARGET ADAPTERS: PlayerController talks to targets through
take_shot_damage(dmg) -> died / take_melee_damage(dmg) -> died. The
Stage-3 archetypes speak richer dialects, so thin adapters translate:
  * Enforcer: forwards the shooter's position and whether the player
    is sliding (slide-under = low attack). A kill is scored EXACTLY
    ONCE: slide kill -> the controller registers Slide & Shoot; melee
    kill -> the controller registers Air Takedown; a pure flank shot
    kill (neither frontal nor slide-under) -> the adapter registers
    SHIELD BYPASS (250, Cyrus's Stage-3 matrix row).
  * Marksman: the archetype ships NO damage methods (Stage-3 gap), so
    the adapter applies plain HP damage and, at zero, the base class's
    own death path (_die). No behaviour is invented — he simply can
    be shot/melee'd like every other target.
  * Boss: forwards damage to BossEnemy's own methods (phase changes,
    events and hud_data stay the boss's own).

SEAMS (honest):
  * phase4/game_entry.launch_stage() is still the per-stage demo
    hook; wiring the menu's stage start to FullGamePipeline is the
    entry point's own step. The pipeline emits its final record in
    exactly the run_record shape VictoryScreen consumes
    ({stage_id, stage_name, t_actual, t_target, combo_peak, completed,
    stunt_breakdown}) with stage_id "full_run", and calls
    VictoryScreen.show_result directly when a screen is injected.
  * save_system.py is owned by the save-system workstream; see
    pipeline_state.SaveBridge for how absence is handled (logged,
    never faked).

Run standalone (human play, all three floors):
    /tmp/ursina-venv/bin/python full_game_pipeline.py
Controls: WASD move, mouse aim, LMB shoot, RMB / F melee, C slide,
L-SHIFT Bullet Time, R reload, Esc quit.
"""

from __future__ import annotations

import logging
import math
import os
import random
import sys
import time as _time
from typing import Callable, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ursina import Entity, Text, Ursina, Vec3, application, camera, color  # noqa: E402
from ursina import destroy, held_keys, mouse  # noqa: E402
from ursina import time as ursina_time  # noqa: E402

from hud.hud_manager import HUDManager  # noqa: E402
from level1.enemy_ai_3d import BulletManager, Guard  # noqa: E402
from level1.lobby_level import LobbyLevel, ThirdPersonCamera  # noqa: E402
from level1.main import GUARD_PATROLS  # noqa: E402
from level1.player_controller_3d import (  # noqa: E402
    SHOT_DAMAGE, PlayerController, PlayerInput)
from logic import take_rating  # noqa: E402
from logic.stunt_manager import STUNT_MATRIX  # noqa: E402
from logic.take_rating import TakeResult  # noqa: E402
from logic.timer_manager import TimerManager  # noqa: E402
from pipeline_state import (  # noqa: E402
    FLOORS_BY_NUMBER, FloorRecord, RunState, SaveBridge)
from stage3.boss_hud import BossHealthBar  # noqa: E402
from stage3.data_center_level import DataCenterLevel  # noqa: E402
from stage3.enemy_archetypes import (  # noqa: E402
    FRONTAL_COS, BossEnemy, EnforcerEnemy, MarksmanEnemy)
from stage3.penthouse_level import PenthouseLevel  # noqa: E402

logger = logging.getLogger(__name__)

# Floor 2's elevator zone (x0, x1, z0, z1) — NOTE: DataCenterLevel
# defines no goal zone of its own (verified in its source: hazards and
# cover only), so the pipeline places Floor 2's elevator at the
# north-east corner, past the glass rooms, under the monitoring wall —
# the same "reach the elevator" win rule as the Lobby. A gold pad
# marks it in the scene so the goal is visible, not implied.
DC_ELEVATOR_ZONE = (16.5, 19.5, 10.0, 12.5)

FLOOR_SPAWNS = {
    1: Vec3(0, 0.9, -12.5),     # Lobby entrance (controller default)
    2: Vec3(0, 0.9, -11.5),     # Data Center south entrance
    3: Vec3(0, 0.9, -13.5),     # Penthouse south glass line
}

STUNT_LABELS = {
    "bullet_dodge": "Bullet Dodge",
    "slide_shoot": "Slide & Shoot",
    "air_takedown": "Air Takedown",
    "wall_run_kill": "Wall-Run Kill",
    "shield_bypass": "Shield Bypass",
    "defenestration": "Defenestration",
}


# ===========================================================================
# Enemy target adapters (see module docstring)
# ===========================================================================
class EnforcerTargetAdapter:
    """EnforcerEnemy through the PlayerController target protocol."""

    def __init__(self, enemy: EnforcerEnemy, player: PlayerController,
                 stunt, hud) -> None:
        self.enemy = enemy
        self.player = player
        self.stunt = stunt
        self.hud = hud
        self.name = enemy.name

    @property
    def alive(self) -> bool:
        return self.enemy.alive

    @property
    def position(self) -> Vec3:
        return self.enemy.position

    def _frontal(self) -> bool:
        rel = self.player.position - self.enemy.position
        rel.y = 0.0
        if rel.length() < 1e-4:
            return False
        return self.enemy.facing.dot(rel.normalized()) > FRONTAL_COS

    def take_shot_damage(self, dmg: float) -> bool:
        low = self.player.is_sliding
        frontal = self._frontal()
        result = self.enemy.take_shot_damage(
            dmg, self.player.position, low_attack=low)
        if result == "dead" and not low and not frontal:
            # Pure flank kill — the Shield Bypass row of the matrix.
            # (Slide kills are scored by the controller as Slide &
            # Shoot; scoring both would pay one kill twice.)
            self.stunt.register("shield_bypass")
            self.hud.notify(STUNT_MATRIX["shield_bypass"], "SHIELD BYPASS")
        return result == "dead"

    def take_melee_damage(self, dmg: float) -> bool:
        result = self.enemy.take_melee_damage(dmg, self.player.position)
        return result == "dead"


class MarksmanTargetAdapter:
    """MarksmanEnemy through the target protocol. The archetype ships
    no damage methods, so the adapter applies plain HP damage and the
    base class's death path — see the module docstring."""

    def __init__(self, enemy: MarksmanEnemy) -> None:
        self.enemy = enemy
        self.name = enemy.name

    @property
    def alive(self) -> bool:
        return self.enemy.alive

    @property
    def position(self) -> Vec3:
        return self.enemy.position

    def _apply(self, dmg: float, source: str) -> bool:
        enemy = self.enemy
        if not enemy.alive:
            return False
        enemy.hp = max(0.0, enemy.hp - float(dmg))
        logger.info("%s took %.0f %s damage -> HP %.0f",
                    enemy.name, dmg, source, enemy.hp)
        if enemy.hp <= 0.0:
            enemy._die(source)
            return True
        return False

    def take_shot_damage(self, dmg: float) -> bool:
        return self._apply(dmg, "shot")

    def take_melee_damage(self, dmg: float) -> bool:
        return self._apply(dmg, "melee")


class BossTargetAdapter:
    """BossEnemy through the target protocol (his own damage methods,
    phase bookkeeping and events untouched)."""

    def __init__(self, enemy: BossEnemy, player: PlayerController) -> None:
        self.enemy = enemy
        self.player = player
        self.name = enemy.name

    @property
    def alive(self) -> bool:
        return self.enemy.alive

    @property
    def position(self) -> Vec3:
        return self.enemy.position

    def take_shot_damage(self, dmg: float) -> bool:
        return self.enemy.take_shot_damage(
            dmg, self.player.position) == "dead"

    def take_melee_damage(self, dmg: float) -> bool:
        return self.enemy.take_melee_damage(
            dmg, self.player.position) == "dead"


# ===========================================================================
# Elevator transition scene
# ===========================================================================
class ElevatorTransition:
    """The between-floors scene state: elevator doors + the finished
    floor's stats panel, driven by the floor's real FloorRecord.

    A real Ursina scene state (UI entities on camera.ui), ticked by the
    pipeline: doors close (first quarter), the ride holds with the
    stats readable (middle half), doors open (last quarter). ``frames``
    counts the frames it actually rendered — the QA test's evidence.
    """

    def __init__(self, duration_s: float = 3.0) -> None:
        self.duration_s = float(duration_s)
        self.root = Entity(parent=camera.ui, enabled=False)
        self._backdrop = Entity(parent=self.root, model="quad",
                                scale=(2.2, 1.3), color=color.rgb(8, 8, 12))
        door_color = color.rgb(70, 74, 86)
        self._door_left = Entity(parent=self.root, model="quad",
                                 scale=(0.56, 1.06), position=(-0.28, 0, 0),
                                 color=door_color)
        self._door_right = Entity(parent=self.root, model="quad",
                                  scale=(0.56, 1.06), position=(0.28, 0, 0),
                                  color=door_color)
        self._panel = Entity(parent=self.root, model="quad",
                             scale=(1.02, 0.66), position=(0, 0, -0.01),
                             color=color.rgb(14, 18, 30))
        self._panel.alpha = 0.92
        self.title_text = Text(parent=self.root, text="", position=(0, 0.27),
                               origin=(0, 0), scale=2.0, color=color.yellow)
        self.stats_text = Text(parent=self.root, text="", position=(0, 0.13),
                               origin=(0, 0.5), scale=1.45, color=color.white)
        self.stats_text_value: str = ""
        self.title_text_value: str = ""
        self.record: Optional[FloorRecord] = None
        self.elapsed: float = 0.0
        self.frames: int = 0
        self.active: bool = False

    # -------------------------------------------------------------- show
    def show(self, record: FloorRecord) -> None:
        """Present the transition for a settled floor record."""
        self.record = record
        r = record
        self.title_text_value = (
            f"ELEVATOR — FLOOR {r.level_num} COMPLETE: {r.stage_name.upper()}")
        self.stats_text_value = (
            f"Time ......... {r.t_actual_s:.2f}s / {r.effective_target_s:.1f}s target\n"
            f"Banked ....... +{r.banked_out_s:.1f}s to the next floor\n"
            f"Floor S_time . {r.s_time:,}\n"
            f"Stunt gained . +{r.stunt_base_gained:,} base "
            f"(run base {r.stunt_base_end:,}, combo x{r.combo_end:.1f})\n"
            f"Floor take ... {r.floor_s_total:,} — RANK {r.floor_rank} "
            f"({r.floor_title})\n"
            f"Heal ......... +{r.heal_applied:.0f} HP -> {r.hp_after_heal:.0f} HP"
        )
        self.title_text.text = self.title_text_value
        self.stats_text.text = self.stats_text_value
        self.elapsed = 0.0
        self.frames = 0
        self.active = True
        self.root.enabled = True
        self._set_doors(0.0)
        logger.info("Elevator transition shown for floor %d (rank %s)",
                    r.level_num, r.floor_rank)

    # -------------------------------------------------------------- tick
    def tick(self, dt: float) -> bool:
        """Advance the scene. Returns True on the tick it completes."""
        if not self.active or dt <= 0:
            return False
        self.elapsed += dt
        self.frames += 1
        frac = min(1.0, self.elapsed / self.duration_s)
        if frac < 0.25:            # doors close
            self._set_doors(frac / 0.25 * 0.0 + (1.0 - frac / 0.25))
        elif frac < 0.75:         # the ride — stats readable
            self._set_doors(0.0)
        else:                     # doors open onto the next floor
            self._set_doors((frac - 0.75) / 0.25)
        if self.elapsed >= self.duration_s:
            self.active = False
            self.root.enabled = False
            return True
        return False

    def _set_doors(self, openness: float) -> None:
        """0.0 = doors fully closed (centre), 1.0 = fully open."""
        offset = 0.28 + 0.58 * max(0.0, min(1.0, openness))
        self._door_left.x = -offset
        self._door_right.x = offset

    def hide(self) -> None:
        self.active = False
        self.root.enabled = False

    def dispose(self) -> None:
        try:
            destroy(self.root)
        except Exception:
            pass


# ===========================================================================
# Floor session
# ===========================================================================
class FloorSession:
    """One floor of the chain, assembled from the studio's modules.

    Mirrors level1.main.GameSession's assembly and tick order, with
    three chain differences: the TimerManager cap is the floor's
    EFFECTIVE target (base + banked), the StuntManager is the run's
    shared one, and the player's HP is seeded from the run state.
    """

    def __init__(self, run_state: RunState, level_num: int) -> None:
        self.run_state = run_state
        self.level_num = level_num
        _n, self.stage_id, self.stage_name, self.base_target_s = \
            FLOORS_BY_NUMBER[level_num]
        self.effective_target_s = run_state.effective_target(
            self.base_target_s)
        self._t0 = _time.perf_counter()

        self.guards: List[Guard] = []
        self.enforcer: Optional[EnforcerEnemy] = None
        self.marksman: Optional[MarksmanEnemy] = None
        self.boss: Optional[BossEnemy] = None
        self.boss_bar: Optional[BossHealthBar] = None
        self.raw_enemies: List = []
        self.targets: List = []
        self.goal_check: Callable[[], bool] = lambda: False
        self.goal_reason: str = ""
        self.on_shot: Optional[Callable[[], None]] = None
        self.cover_router: Optional[Callable[[str], None]] = None
        self.level_tick: Optional[Callable[[float], None]] = None

        self.level = self._build_level()
        self.world = self.level.world
        self.camera_rig = getattr(self.level, "camera_rig", None) \
            or ThirdPersonCamera()

        self.timer = TimerManager(
            lambda: _time.perf_counter() - self._t0,
            self.effective_target_s)
        run_state.attach_timer(self.timer)
        self.stunt_base_start = run_state.stunt.raw_base_total

        self.hud = HUDManager(target_s=self.effective_target_s)
        self.player = PlayerController(self.world, run_state.stunt,
                                       self.hud,
                                       spawn=FLOOR_SPAWNS[level_num])
        self.player.hp = run_state.hp
        self._arm_floor()
        self.player.targets = self.targets

        self.bullets = BulletManager(self.world)
        self.bullets.on_dodge = lambda pts, label: self.hud.notify(pts, label)

        self.state: str = "playing"          # playing | won | lost
        self.won: bool = False
        self.reason: str = ""
        self.frames: int = 0
        self._last_shots_fired: int = 0

        self.timer.start()
        logger.info("Floor %d (%s) started: effective target %.1fs "
                    "(base %.0f + banked %.1f), HP %.0f",
                    level_num, self.stage_name, self.effective_target_s,
                    self.base_target_s,
                    self.effective_target_s - self.base_target_s,
                    self.player.hp)

    # ------------------------------------------------------------- build
    def _build_level(self):
        if self.level_num == 1:
            return LobbyLevel()
        if self.level_num == 2:
            return DataCenterLevel()
        return PenthouseLevel()

    def _arm_floor(self) -> None:
        if self.level_num == 1:
            self._arm_lobby()
        elif self.level_num == 2:
            self._arm_data_center()
        else:
            self._arm_penthouse()

    def _arm_lobby(self) -> None:
        rng = random.Random(20261027)
        self.guards = [Guard(self.world, name, points, rng)
                       for name, points in GUARD_PATROLS]
        self.raw_enemies = list(self.guards)
        self.targets = list(self.guards)
        level = self.level
        self.goal_check = lambda: level.point_in_goal(self.player.position)
        self.goal_reason = "Elevator reached"
        guards = self.guards
        player = self.player
        self.on_shot = lambda: [g.hear_gunshot(player.position)
                                for g in guards]

    def _arm_data_center(self) -> None:
        level: DataCenterLevel = self.level
        rng = random.Random(20261028)
        self.enforcer = EnforcerEnemy(self.world, "ENF-DC",
                                      Vec3(-11, 0.9, 0), facing_yaw=90.0,
                                      rng=rng)
        self.marksman = MarksmanEnemy(self.world, "MRK-DC",
                                      Vec3(17, 0.9, 10))
        self.marksman.damage_sink = self.player.take_damage
        level.register_enemy(self.enforcer)
        level.register_enemy(self.marksman)
        self.raw_enemies = [self.enforcer, self.marksman]
        self.targets = [
            EnforcerTargetAdapter(self.enforcer, self.player,
                                  self.run_state.stunt, self.hud),
            MarksmanTargetAdapter(self.marksman),
        ]
        # The floor's elevator: a gold pad in the NE corner (see the
        # DC_ELEVATOR_ZONE note at the top of this module).
        x0, x1, z0, z1 = DC_ELEVATOR_ZONE
        pad = Entity(model="quad", scale=(x1 - x0, z1 - z0, 1.0),
                     rotation_x=90,
                     position=((x0 + x1) / 2, 0.06, (z0 + z1) / 2),
                     color=color.rgb(198, 158, 60))
        level.entities.append(pad)
        self.goal_check = lambda: (
            x0 <= self.player.position.x <= x1
            and z0 <= self.player.position.z <= z1)
        self.goal_reason = "Elevator reached"
        self.on_shot = lambda: level.note_gunfire(self.player.position)
        self.cover_router = self._dc_cover_router
        self.level_tick = level.tick

    def _dc_cover_router(self, solid_name: str) -> None:
        """Route a hitscan cover hit into Floor 2's interactive
        objects: server racks (electric hazards) and destructible
        cover — the routing the level's docstring assigns here."""
        level: DataCenterLevel = self.level
        for rack in level.racks:
            if rack.name == solid_name:
                rack.take_shot_damage(SHOT_DAMAGE)
                return
        for cover in level.covers:
            if cover.name == solid_name:
                cover.take_damage(SHOT_DAMAGE)
                return

    def _arm_penthouse(self) -> None:
        level: PenthouseLevel = self.level
        self.boss = BossEnemy(self.world, "BOSS", Vec3(0, 0.9, 10),
                              cover_points=[Vec3(-8, 0, 10), Vec3(8, 0, 10),
                                            Vec3(0, 0, 13)],
                              rng=random.Random(99))
        self.marksman = MarksmanEnemy(self.world, "MRK-PH",
                                      Vec3(18, 0.9, -12))
        self.marksman.damage_sink = self.player.take_damage
        self.raw_enemies = [self.boss, self.marksman]
        self.targets = [
            BossTargetAdapter(self.boss, self.player),
            MarksmanTargetAdapter(self.marksman),
        ]
        self.boss_bar = BossHealthBar()
        self.boss_bar.begin_fight(self.boss)
        boss = self.boss
        self.goal_check = lambda: not boss.alive
        self.goal_reason = "Syndicate Boss defeated"
        self.cover_router = self._ph_cover_router
        self.level_tick = level.tick

    def _ph_cover_router(self, solid_name: str) -> None:
        """Route a hitscan cover hit on Floor 3: destructible cover
        takes damage; a window pane hit by a shot shatters."""
        level: PenthouseLevel = self.level
        for cover in level.covers:
            if cover.name == solid_name:
                cover.take_damage(SHOT_DAMAGE)
                return
        for pane in level.panes:
            if pane.solid.name == solid_name:
                pane.break_pane()
                return

    # ---------------------------------------------------------------- tick
    def tick(self, dt: float, inp: PlayerInput) -> None:
        if self.state != "playing" or dt <= 0:
            return
        self.frames += 1
        world_dt = dt * self.player.time_scale
        self.player.tick(dt, inp)
        self._route_shots()
        for enemy in self.raw_enemies:
            enemy.tick(world_dt, self.player.position,
                       not self.player.dead, self.bullets)
        self.bullets.tick(world_dt, self.player, self.run_state.stunt,
                          self.player.bt_active)
        if self.level_tick is not None:
            self.level_tick(world_dt)
        if self.boss_bar is not None:
            self.boss_bar.update()
        self.camera_rig.update(self.player.position, self.player.aim_yaw,
                               self.player.aim_pitch)
        self.hud.update_state(
            hp=self.player.hp,
            bullet_charge=self.player.charge,
            elapsed_s=self.timer.elapsed,
            target_s=self.effective_target_s,
            stunt_score=self.run_state.stunt.current_score,
            combo=self.run_state.stunt.combo_multiplier,
            last_actions=self.run_state.stunt.recent_actions,
        )
        self.run_state.observe_combo()
        if self.player.dead:
            self._end(False, "Player down — HP reached zero")
        elif self.goal_check():
            self._end(True, self.goal_reason)
        elif self.timer.elapsed >= self.effective_target_s:
            self._end(False, "Time target exceeded")

    def _route_shots(self) -> None:
        """Per new shot fired this tick: alert/report gunfire, then
        route a cover hit into the floor's interactive objects.
        (The controller's fire interval exceeds the max tick step, so
        at most one shot lands per tick and last_shot is exact.)"""
        fired = self.player.shots_fired
        if fired == self._last_shots_fired:
            return
        self._last_shots_fired = fired
        if self.on_shot is not None:
            self.on_shot()
        shot = self.player.last_shot
        if shot.get("kind") == "cover" and self.cover_router is not None:
            self.cover_router(str(shot.get("solid")))

    def _end(self, won: bool, reason: str) -> None:
        self.won = won
        self.reason = reason
        self.state = "won" if won else "lost"
        self.timer.finish()
        logger.info("Floor %d %s: %s (%.2fs)",
                    self.level_num, self.state, reason, self.timer.elapsed)

    # ------------------------------------------------------------ teardown
    def teardown(self) -> None:
        """Destroy every entity this session created, so the next
        floor (or the final card) renders over a clean scene."""
        if self.boss_bar is not None:
            self.boss_bar.end_fight()
        collected: List = []
        seen = set()

        def add(ent) -> None:
            if ent is not None and id(ent) not in seen:
                seen.add(id(ent))
                collected.append(ent)

        for ent in getattr(self.level, "entities", []):
            add(ent)
        for pane in getattr(self.level, "panes", []):
            add(pane.entity)
            for shard in pane.shards:
                add(shard)
        for cover in getattr(self.level, "covers", []):
            add(cover.entity)
            for chunk in cover.debris:
                add(chunk)
        add(self.player.entity)
        for child in list(self.player.entity.children):
            add(child)
        for tracer in self.player._tracers:
            add(tracer["entity"])
        for bullet in self.bullets.bullets:
            add(bullet.entity)
        for enemy in self.raw_enemies:
            add(enemy.entity)
            for child in list(enemy.entity.children):
                add(child)
            for extra in ("laser_entity", "_tracer"):
                add(getattr(enemy, extra, None))
            for cloud in getattr(enemy, "smoke_clouds", []):
                add(cloud.entity)
        for value in vars(self.hud).values():
            if isinstance(value, Entity) and value is not camera.ui:
                add(value)
            elif isinstance(value, list):
                for item in value:
                    add(getattr(item, "text", None))
        if self.boss_bar is not None:
            for attr in ("_name_text", "_bg", "_fill", "_hp_text"):
                add(getattr(self.boss_bar, attr, None))
        for ent in collected:
            try:
                destroy(ent)
            except Exception:
                pass
        logger.info("Floor %d scene torn down (%d entities)",
                    self.level_num, len(collected))


# ===========================================================================
# The pipeline
# ===========================================================================
class FullGamePipeline:
    """Drives the whole chain: floors, elevator transitions, the
    final card. Construct after the Ursina app exists.

    Parameters
    ----------
    start_floor:
        Level-select entry: 1 (default), 2 or 3. Starting above 1
        begins there with a fresh RunState; when the save system is
        present, a locked floor raises ValueError instead of starting.
    victory_screen:
        Optional phase4 VictoryScreen; at run end it receives
        show_result(final_result, final_run_record).
    save_bridge:
        Optional pipeline_state.SaveBridge (a fresh one is created
        otherwise) — injectable so tests can audit the save calls.
    """

    def __init__(self, start_floor: int = 1, victory_screen=None,
                 save_bridge: Optional[SaveBridge] = None,
                 transition_seconds: float = 3.0) -> None:
        if start_floor not in FLOORS_BY_NUMBER:
            raise ValueError(f"start_floor must be one of "
                             f"{sorted(FLOORS_BY_NUMBER)}, got {start_floor}")
        self.save = save_bridge if save_bridge is not None else SaveBridge()
        self.unlock_note: Optional[str] = None
        if start_floor > 1:
            unlocked = self.save.is_unlocked(start_floor)
            if unlocked is False:
                raise ValueError(
                    f"Floor {start_floor} is locked in the save data — "
                    f"level-select entry refused")
            if unlocked is None:
                self.unlock_note = (
                    "save_system absent: level-select unlock state "
                    "could not be verified; entry allowed and logged")
                logger.warning(self.unlock_note)
        self.run_state = RunState(start_floor=start_floor)
        self.victory_screen = victory_screen
        self.transition = ElevatorTransition(duration_s=transition_seconds)
        self.session: Optional[FloorSession] = None
        self.phase: str = "floor"      # floor | transition | final | failed
        self.final_result: Optional[TakeResult] = None
        self.final_record: Optional[dict] = None
        self.final_run_record: Optional[dict] = None
        self.total_frames: int = 0
        self._next_floor: Optional[int] = None
        self._start_floor(start_floor)

    # ------------------------------------------------------------ floors
    @property
    def current_floor_num(self) -> Optional[int]:
        return self.session.level_num if self.session is not None else None

    def _start_floor(self, level_num: int) -> None:
        self.session = FloorSession(self.run_state, level_num)
        self.phase = "floor"
        logger.info("Pipeline: floor %d live", level_num)

    def tick(self, dt: float, inp: Optional[PlayerInput] = None) -> None:
        """Advance the whole game by one frame."""
        if dt <= 0:
            return
        self.total_frames += 1
        if self.phase == "floor" and self.session is not None:
            self.session.tick(dt, inp or PlayerInput())
            if self.session.state != "playing":
                self._settle_current_floor()
        elif self.phase == "transition":
            if self.transition.tick(dt):
                nxt = self._next_floor
                self._next_floor = None
                self._start_floor(nxt)

    # ------------------------------------------------------------- settle
    def _settle_current_floor(self) -> None:
        session = self.session
        assert session is not None
        boss_defeated: Optional[bool] = None
        if session.boss is not None:
            boss_defeated = not session.boss.alive
        record = self.run_state.settle_floor(
            level_num=session.level_num,
            timer=session.timer,
            won=session.won,
            reason=session.reason,
            hp_end_pre_heal=session.player.hp,
            stunt_base_start=session.stunt_base_start,
            boss_defeated=boss_defeated,
        )
        # Save wiring (integration note): AFTER the take is rated.
        record.save_call = self.save.save_floor_result(
            record.level_num, record.floor_s_total,
            record.t_actual_s, record.floor_rank)
        session.teardown()
        self.session = None
        if not self.run_state.chain_failed and record.level_num < 3:
            self._next_floor = record.level_num + 1
            self.transition.show(record)
            self.phase = "transition"
        else:
            self._finish_run()

    # --------------------------------------------------------------- final
    def _finish_run(self) -> None:
        run = self.run_state
        result, total_s_time = run.final_evaluation()
        failed = run.chain_failed
        if failed:
            # Numeric total stands; rank/title forced to the F take
            # (the level1 convention for a failed run).
            result = TakeResult(
                s_time=result.s_time,
                stunt_base=result.stunt_base,
                combo_multiplier=result.combo_multiplier,
                stunt_component=result.stunt_component,
                total=result.total,
                rank=take_rating.FAIL_RANK,
                title=take_rating.FAIL_TITLE,
            )
        self.final_result = result
        counts: dict = {}
        order: List[str] = []
        for event in run.stunt.events:
            if event.action_type not in counts:
                counts[event.action_type] = 0
                order.append(event.action_type)
            counts[event.action_type] += 1
        breakdown = [f"{STUNT_LABELS.get(a, a)} x{counts[a]}"
                     for a in order]
        if run.stunt.multi_kill_bonuses:
            breakdown.append(
                f"Multi-Kill bonuses x{len(run.stunt.multi_kill_bonuses)}")
        self.final_run_record = {
            "stage_id": "full_run",
            "stage_name": "NYC Siege — Full Run",
            "t_actual": round(sum(r.t_actual_s
                                   for r in run.floor_records), 2),
            "t_target": round(sum(r.effective_target_s
                                  for r in run.floor_records), 2),
            "combo_peak": run.combo_peak,
            "completed": not failed,
            "stunt_breakdown": breakdown,
        }
        self.final_record = {
            "outcome": "FAILED" if failed else "COMPLETE",
            "failed_at_floor": run.failed_at_floor,
            "floors": [r.to_dict() for r in run.floor_records],
            "s_time_total": total_s_time,
            "stunt_base": result.stunt_base,
            "combo": result.combo_multiplier,
            "stunt_component": result.stunt_component,
            "s_total": result.total,
            "rank": result.rank,
            "title": result.title,
            "save_system_present": self.save.present,
            "save_calls": list(self.save.calls),
        }
        self.phase = "failed" if failed else "final"
        logger.info("Run %s: S_total %d rank %s (%s)",
                    self.final_record["outcome"], result.total,
                    result.rank, result.title)
        if self.victory_screen is not None:
            self.victory_screen.show_result(result, self.final_run_record)

    def dispose(self) -> None:
        """Tear down the live floor (if any) and the transition —
        used by the standalone entry's Re-take path."""
        if self.session is not None:
            self.session.teardown()
            self.session = None
        self.transition.dispose()


# ===========================================================================
# Human entry point (standalone play; the QA test imports the pipeline
# and drives it with a scripted autopilot instead).
# ===========================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    from phase4.game_ui_screens import VictoryScreen

    app = Ursina(title="Action Star: NYC Siege 3D — Full Game",
                 vsync=False)
    holder: dict = {}

    def _restart(_stage_id=None) -> None:
        old = holder.get("pipeline")
        if old is not None:
            old.dispose()
        holder["pipeline"] = FullGamePipeline(
            start_floor=1,
            victory_screen=VictoryScreen(
                on_retake=_restart,
                on_menu=lambda: application.quit()))

    _restart()
    mouse.locked = True
    _edges = {"slide": False, "melee": False, "bullet_time": False,
              "reload": False}
    _aim = {"yaw": 0.0, "pitch": 0.0}

    def input(key):  # noqa: A001 — Ursina's input hook name
        if key in ("left shift", "shift"):
            _edges["bullet_time"] = True
        elif key == "c":
            _edges["slide"] = True
        elif key in ("right mouse down", "f"):
            _edges["melee"] = True
        elif key == "r":
            _edges["reload"] = True
        elif key == "escape":
            application.quit()

    def _build_input() -> PlayerInput:
        pipeline = holder["pipeline"]
        if pipeline.phase != "floor":
            return PlayerInput()
        try:
            vel = getattr(mouse, "velocity", None)
            vx = float(vel[0]) if vel is not None else float(
                getattr(mouse, "velocity_x", 0.0))
            vy = float(vel[1]) if vel is not None else float(
                getattr(mouse, "velocity_y", 0.0))
            _aim["yaw"] += vx * 55.0
            _aim["pitch"] = max(-40.0, min(40.0, _aim["pitch"] - vy * 55.0))
        except Exception:
            pass
        yaw = math.radians(_aim["yaw"])
        fwd = Vec3(math.sin(yaw), 0, math.cos(yaw))
        right = Vec3(math.cos(yaw), 0, -math.sin(yaw))
        move = Vec3(0, 0, 0)
        if held_keys["w"]:
            move += fwd
        if held_keys["s"]:
            move -= fwd
        if held_keys["d"]:
            move += right
        if held_keys["a"]:
            move -= right
        inp = PlayerInput(
            move=move,
            aim_yaw=_aim["yaw"],
            aim_pitch=_aim["pitch"],
            shoot=bool(held_keys["left mouse"]),
            melee=_edges["melee"],
            slide=_edges["slide"],
            bullet_time=_edges["bullet_time"],
            reload=_edges["reload"],
        )
        for name in _edges:
            _edges[name] = False
        return inp

    def update():
        holder["pipeline"].tick(min(ursina_time.dt, 0.05), _build_input())

    app.run()
