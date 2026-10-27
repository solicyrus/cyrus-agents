"""Action Star: NYC Siege 3D — Level 1: Tower Lobby (assembly + entry).

``GameSession`` assembles the whole level from the studio's modules:

  * level1.lobby_level.LobbyLevel ......... geometry, collision, camera
  * level1.player_controller_3d ........... the action star
  * level1.enemy_ai_3d .................... 3 armed guards + projectiles
  * hud.hud_manager.HUDManager ............ live HUD
  * logic.timer_manager.TimerManager ...... the 90 s target clock
  * logic.stunt_manager.StuntManager ...... stunt score / combo
  * logic.take_rating ..................... Final Take Rating at the end

WIN: reach the elevator goal zone (after clearing OR slipping past the
guards). LOSE: HP reaches zero, or the 90 s target passes (stage
failed, graded F / "Re-take Required" by rule; the numeric breakdown is
still recorded). On either ending the session freezes and produces the
final report card from the LIVE state — the same card the QA smoke test
verifies field by field.

The assembly lives in a class (not at import time) so the QA test can
build the identical game headlessly and drive it with scripted input.
Running this file directly is the human game:

    /tmp/ursina-venv/bin/python level1/main.py

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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ursina import Text, Ursina, Vec3, application, camera, color, held_keys, mouse  # noqa: E402
from ursina import time as ursina_time  # noqa: E402

from hud.hud_manager import HUDManager  # noqa: E402
from level1.enemy_ai_3d import BulletManager, Guard  # noqa: E402
from level1.lobby_level import LobbyLevel  # noqa: E402
from level1.player_controller_3d import PlayerController, PlayerInput  # noqa: E402
from logic import take_rating  # noqa: E402
from logic.stunt_manager import StuntManager  # noqa: E402
from logic.timer_manager import TimerManager  # noqa: E402

logger = logging.getLogger(__name__)

# Level 1 (Lobby) target time — approved by Cyrus 2026-10-27.
TARGET_TIME_S = 90.0

GUARD_PATROLS = (
    ("G1", [Vec3(-14, 0, -2), Vec3(-14, 0, 6)]),     # west flank
    ("G2", [Vec3(12, 0, -6), Vec3(12, 0, 2)]),       # east / centre
    ("G3", [Vec3(-5, 0, 11), Vec3(5, 0, 11)]),       # elevator guard
)


class GameSession:
    """One playable run of Level 1. Construct after the Ursina app."""

    def __init__(self) -> None:
        self.level = LobbyLevel()
        self._t0 = _time.perf_counter()
        self.timer = TimerManager(lambda: _time.perf_counter() - self._t0,
                                  TARGET_TIME_S)
        self.stunt = StuntManager(clock=lambda: self.timer.elapsed)
        self.hud = HUDManager(target_s=TARGET_TIME_S)
        self.player = PlayerController(self.level.world, self.stunt, self.hud)

        rng = random.Random(20261027)
        self.guards = [Guard(self.level.world, name, points, rng)
                       for name, points in GUARD_PATROLS]
        self.player.targets = self.guards
        self.player.on_shoot = self._alert_guards_to_shot

        self.bullets = BulletManager(self.level.world)
        self.bullets.on_dodge = lambda pts, label: self.hud.notify(pts, label)

        self.state: str = "playing"          # playing | won | lost
        self.result = None                   # TakeResult from take_rating
        self.final_record: dict = {}
        self.final_card_text: str = ""
        self._overlay = Text(text="", position=(0, 0.1), origin=(0, 0),
                             scale=1.9, color=color.white,
                             parent=camera.ui, enabled=False)

        self.timer.start()
        logger.info("Level 1 session started (target %.0fs)", TARGET_TIME_S)

    # -------------------------------------------------------------- wiring
    def _alert_guards_to_shot(self) -> None:
        for guard in self.guards:
            guard.hear_gunshot(self.player.position)

    @property
    def world_time_scale(self) -> float:
        """0.3 while Bullet Time is active, else 1.0 (test/QA evidence)."""
        return self.player.time_scale

    # ----------------------------------------------------------------- tick
    def tick(self, dt: float, inp: PlayerInput) -> None:
        if self.state != "playing" or dt <= 0:
            return
        world_dt = dt * self.player.time_scale
        self.player.tick(dt, inp)
        for guard in self.guards:
            guard.tick(world_dt, self.player.position,
                       not self.player.dead, self.bullets)
        self.bullets.tick(world_dt, self.player, self.stunt,
                          self.player.bt_active)
        self.level.camera_rig.update(self.player.position,
                                     self.player.aim_yaw,
                                     self.player.aim_pitch)
        self.hud.update_state(
            hp=self.player.hp,
            bullet_charge=self.player.charge,
            elapsed_s=self.timer.elapsed,
            target_s=TARGET_TIME_S,
            stunt_score=self.stunt.current_score,
            combo=self.stunt.combo_multiplier,
            last_actions=self.stunt.recent_actions,
        )
        if self.player.dead:
            self._finish(won=False, reason="Player down — HP reached zero")
        elif self.level.point_in_goal(self.player.position):
            self._finish(won=True, reason="Elevator reached")
        elif self.timer.elapsed >= TARGET_TIME_S:
            self._finish(won=False, reason="Time target exceeded")

    # ---------------------------------------------------------------- finish
    def _finish(self, won: bool, reason: str) -> None:
        final_elapsed = self.timer.finish()
        evaluated = take_rating.evaluate(
            self.timer.time_bonus(),
            self.stunt.raw_base_total,
            self.stunt.combo_multiplier,
        )
        self.result = evaluated
        if won:
            self.state = "won"
            rank, title = evaluated.rank, evaluated.title
        else:
            self.state = "lost"
            rank, title = take_rating.FAIL_RANK, take_rating.FAIL_TITLE
        self.final_record = {
            "outcome": "WIN" if won else "FAILED",
            "reason": reason,
            "elapsed_s": round(final_elapsed, 2),
            "target_s": TARGET_TIME_S,
            "hp": round(self.player.hp, 1),
            "bullet_charge": round(self.player.charge, 1),
            "stunt_score": self.stunt.current_score,
            "stunt_base": evaluated.stunt_base,
            "combo": self.stunt.combo_multiplier,
            "s_time": evaluated.s_time,
            "s_total": evaluated.total,
            "rank": rank,
            "title": title,
        }
        r = self.final_record
        self.final_card_text = (
            "=========== FINAL TAKE — LEVEL 1: TOWER LOBBY ===========\n"
            f"Outcome ....... {r['outcome']} ({reason})\n"
            f"Time .......... {r['elapsed_s']:.2f}s / Target "
            f"{r['target_s']:.2f}s\n"
            f"HP ............ {r['hp']:.1f}%\n"
            f"Bullet Time ... {r['bullet_charge']:.1f}% charge\n"
            f"Stunt Score ... {r['stunt_score']:,} (base "
            f"{r['stunt_base']:,} x combo {r['combo']:.1f})\n"
            f"S_time ........ {r['s_time']:,}\n"
            f"S_total ....... {r['s_total']:,}\n"
            f"RANK .......... {rank} — {title}\n"
            "==========================================================="
        )
        self._overlay.text = self.final_card_text
        self._overlay.enabled = True
        logger.info("Stage %s: %s", self.state, reason)
        print(self.final_card_text, flush=True)


# ---------------------------------------------------------------------------
# Human entry point (only when run as a script; the QA test imports the
# session and drives it with scripted PlayerInput instead).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = Ursina(title="Action Star: NYC Siege 3D — Level 1: Tower Lobby",
                 vsync=False)
    session = GameSession()
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
        # dt clamped: a hitching frame must never step physics farther
        # than the thinnest furniture, or the player tunnels through it.
        session.tick(min(ursina_time.dt, 0.05), _build_input())

    app.run()
