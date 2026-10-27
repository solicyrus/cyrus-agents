# Action Star: NYC Siege 3D — 3D Feasibility Report (Stage 1)

> گزارش امکان‌سنجی سه‌بعدی — نتیجه‌ی واقعیِ تست اجرا در همین محیط. خلاصه: ساخت بازی سه‌بعدی با Ursina در این استودیو **ممکن و ثابت‌شده** است؛ نمونه‌ی اولیه واقعاً اجرا شد.

## Verdict
**YES — this studio can build real 3D with Ursina here.** A complete prototype
script was written, installed against, and actually RUN in this sandbox under a
virtual display (Xvfb): it opened a real GLX graphics context, rendered frames,
exercised the Bullet Time and stunt-scoring logic, and quit cleanly with exit
code 0. Details and limits below — nothing in this file is a promise; every line
is a recorded result.

## Environment record
- Scratch venv: `/tmp/ursina-venv` (Python 3.12.3)
- `pip install ursina` → **success**
  - ursina **8.3.0**
  - Panda3D **1.10.16** (ursina's engine dependency)
- Audio: the sandbox has no audio device; Panda3D fell back to NullAudioManager
  with warnings only. Sound is therefore UNTESTED here (needs a real machine).

## The prototype — `prototype3d.py` (this folder)
Complete, runnable, placeholder-free. It implements the Stage-1 mechanics:
- Third-person-ish 3D scene: floor slab + skyscraper blocks, player cube moved
  with WASD, camera following behind/above the player.
- Bullet Time: Space toggles a global time factor 1.0 → 0.3; the world
  (patrolling guard, incoming bullets) runs on scaled time, the player stays on
  real time — exactly the GDD rule.
- Time-Attack: on-screen count-up run timer (mm:ss.t).
- Stunt tie-in: a bullet passing the player during Bullet Time registers
  **Bullet Dodge +50** (first row of the GDD Stunt Matrix).
- A scripted autopilot (`PROTOTYPE_AUTOTEST=1`) drives the same code paths for
  headless runs; without it the game is manual-only.

## Headless run record (verbatim proof lines)
Command: `PROTOTYPE_AUTOTEST=1 xvfb-run -a python prototype3d.py`

```
EVENT bullet_time=ON t=1.52s
EVENT bullet_dodge +50 t=1.53s
EVENT bullet_time=OFF t=3.23s
PROOF frames=176 elapsed=4.51s player_moved=31.48 units dodges=1 stunt_score=50
PROOF prototype ran, rendered and quit cleanly
```
- Exit code: **0** (clean self-quit after the 4.5 s autotest window)
- Graphics pipe: `glxGraphicsPipe` (a real OpenGL context on the virtual display)
- Frame rate: 176 frames / 4.51 s ≈ **39 fps under software rendering** — this
  number describes the sandbox's CPU renderer only; it is NOT a prediction of
  performance on a real GPU machine.

## What can vs. cannot be verified headless
CAN (proven here):
- py_compile and import of full Ursina projects.
- Real engine runs under Xvfb: rendering, update loop, input-state logic,
  timers, time-scaling, event/scoring logic — via the autotest driver.
- Deterministic QA gates (placeholder scan, cross-module consistency) exactly
  as the studio's 2D pipeline already does.

NEEDS a real screen / real machine (NOT proven here):
- Human feel of keyboard/mouse controls and camera behaviour.
- True FPS and visual quality on a GPU (Cyrus's PC).
- Audio playback (no audio device in this sandbox).

## Recommended staged build plan for Level 1 (slice by slice)
Each slice follows the studio law: designer spec → developer code → consistency
gate → QA headless autotest → only then shown to Cyrus. No slice starts before
the previous one passes QA.

- **Slice 0 — Skeleton:** project layout (config / entities / main modules) and
  this prototype's proven systems promoted into modules.
- **Slice 1 — Lobby greybox (Floor 1):** WASD + third-person camera, count-up
  timer, reach the exit pad = win; no combat yet.
- **Slice 2 — Combat core:** shooting + melee, health, one guard enemy type
  with patrol + fire behaviour (extends the prototype's guard/bullets).
- **Slice 3 — Bullet Time system:** GDD physics exactly — 0.3x world scale,
  energy drain 10%/s, recharge 5%/s, 5 s cooldown, Q key, player exempt.
- **Slice 4 — StuntManager:** the full Stunt Matrix events, combo/diversity
  multiplier (+0.5 per action differing from the last 3, cap 5.0, reset on
  hit), Final Take Rating = Base Time Bonus + Stunt Score, S/A/B/C/F ranks,
  best-time record saved between runs.
- **Slice 5 — The tower:** Floors 2–5 per the GDD (offices stealth, security
  room, executive suites, rooftop escape), floor transitions, remaining enemy
  types, lose conditions (health zero / caught by security).
- **Slice 6 — QA & polish gate:** line-by-line review, headless autotest suite
  per slice, then a real-screen check on an actual PC before any "it works"
  claim about feel or performance.

Note (honest scope): the studio's developer agent currently generates Pygame
projects. Extending it to emit Ursina modules is Stage-2 work and was NOT done
in this stage, per the stage plan.
