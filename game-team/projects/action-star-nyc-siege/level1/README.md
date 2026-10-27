# Level 1 — Tower Lobby (Stage 2 build)

Third-person 3D action level in Ursina: fight or slip past three armed
guards across a marble tower lobby and reach the elevator before the
90-second target.

**Level 1 target time: 90s — approved by Cyrus 2026-10-27.**

## Files

| File | Role |
|---|---|
| `lobby_level.py` | The 3D lobby (floor/walls, marble columns, glass entrance, reception desk, planters/consoles as cover, elevator goal zone), the shared `CollisionWorld` (AABB solids, axis-separated circle movement, cover ray queries), cinematic warm/cool lighting, third-person camera rig. |
| `player_controller_3d.py` | WASD + mouse third-person controller: hitscan shooting with tracer + ammo/reload, melee, timed slide, Bullet Time on **L-SHIFT** (GDD physics: world 0.3×, drain 10%/s, recharge 5%/s, 5s cooldown, player exempt). Wired directly to the project's `StuntManager` + `HUDManager`. |
| `enemy_ai_3d.py` | Three armed guards: patrol → alert (sight or gunshot) → engage; real projectile bullets with travel + hit detection that the Bullet-Dodge logic reads. |
| `main.py` | Assembly (`GameSession`): level + player + guards + HUD + `TimerManager(90s)`. WIN = reach the elevator zone → Final Take Rating from `logic/take_rating.py`; LOSE = HP zero, or time-out (F path). Human entry point under `__main__`. |
| `test_level1_smoke.py` | Headless QA autopilot — drives every mechanic and Cyrus's three acceptance gates; prints PROOF lines. |
| `TEST-REPORT.md` | The real run evidence: gate sections, per-mechanic proofs, verbatim Final Take card. |

Scoring, timer and HUD are **imported** from the project's `logic/` and
`hud/` packages (Stage 1) — never duplicated here.

## Controls (human play)

| Input | Action |
|---|---|
| WASD / mouse | Move / aim |
| Left mouse | Shoot (hitscan) |
| Right mouse or F | Melee |
| C | Slide |
| **L-SHIFT** | Bullet Time (hold-free toggle) |
| R | Reload |
| Esc | Quit |

## Run it

```bash
# needs the Ursina environment (ursina 8.3.0 / Panda3D 1.10.16)
python level1/main.py            # human play (real display)

# headless QA (Xvfb):
xvfb-run -a python level1/test_level1_smoke.py
```

## Honest limits

- All FPS figures in `TEST-REPORT.md` were measured under Xvfb with
  Mesa **software rendering** — they prove stability of the Bullet
  Time switch, not real-GPU performance.
- The sandbox has **no audio device** (NullAudioManager): sound is
  unverified.
- Human control/camera feel cannot be verified headless; it needs a
  real-machine play session.
- Frame `dt` is clamped (0.05s in `main.py`, 1/30s in the test): a
  hitching frame must never step physics through furniture — an early
  unclamped build tunneled the player through the reception desk
  during sandbox shader-compilation stalls (see TEST-REPORT.md).
- Gameplay fact found by QA, not a bug: the reception desk is 1.15u
  high, so a standing guard's **chest is not covered** by it — only
  the lower body is. Cover choice matters when aiming/being aimed at.
