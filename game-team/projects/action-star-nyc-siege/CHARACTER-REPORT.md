# CHARACTER REPORT — The Action Star build (2026-10-27)

Cyrus's absolute green light («چراغ سبز مطلق بساز»): the protagonist,
the wall-run, the over-the-shoulder camera and the official fiction —
all four parts built, all proven by real headless runs
(`test_character.py`, 40 main checks + a 10-check intro subprocess),
with the full regression battery re-run afterwards.

## 1. The character model — `character_model.py` (NEW)

`ActionStarModel`: a code-built stylized humanoid from Ursina
primitives — its docstring states honestly: **code-built stylized
model v1, NOT a rigged/skeletal asset** (poses are deterministic part
transforms; no imported mesh, no bone rig).

Structure: the model root IS the player entity (collision semantics
unchanged) → pose rig → torso group (chest, chest plate, belt, head,
hair, both arms) + one leg pivot per side (thigh, boot, **holster +
pistol grip on EACH thigh**). **26 named parts**, inventoried by the
test. Look per spec: near-black tactical body, darker chest plate,
skin head, near-black fingerless-glove hand blocks, pistol in the
right hand.

Poses (all 7 proven with distinct measured transform signatures):
IDLE · RUN (procedural limb swing in `update`) · AIM (right arm
−90°) · SLIDE (rig drops 0.52, pitches −32°) · MELEE (torso yaw 28°,
arm −150°) · WALLRUN (rig banks −18° × wall side, toward the wall;
sign flips with side) · DODGE (rig roll −14°). The controller drives
poses every tick: WALLRUN > SLIDE > MELEE (0.3 s strike window) >
DODGE (Bullet Time + moving) > AIM (shoot held) > RUN > IDLE. The
old capsule "squash" slide visual is gone — the slide is the pose.

## 2. Wall-Run — in `level1/player_controller_3d.py`

Attach: moving beside a wall within probe reach while travelling
parallel to it. While attached: gravity suspended at a fixed height,
body banked (pose + model), movement continues along the wall.

Measured (lobby west wall, scripted):
- attached span **1.81 s of controller tick time** — Cyrus's cap
  **1.8 s** enforced (the C# reference's tuning value, superseding
  the brief's 2.5 s);
- height held in **[1.42, 1.50]** while attached; travel along the
  wall **12.7 u** in one run;
- **stick: wall gap exactly 0.350 on every settled sample** — no
  drift away, no clipping in;
- detach on cap / input stop / turn-away / slide, with a 0.35 s
  re-attach lockout; landing is clean (y returns to 0.90, no sink).
- **Wall jump** (Space mid-run): impulse up + away + forward —
  airborne observed, apex **y 2.05**, away drift **2.89 u**, state
  cleared, clean landing.
- **Wall-run kill**: a shot kill mid-run registered `wall_run_kill`
  exactly once — base **200**, awarded **300 at ×1.5 combo**, the
  StuntManager score equalled an independent recomputation, and the
  HUD feed showed "+200 PTS ⚡ WALL-RUN KILL". Melee kills mid-run
  take the same stunt (slide priority preserved).

### SCORING DIVERGENCE from Cyrus's Unity C# reference (deliberate)

The C# sample awards **+200 on wall-run START** and invents
**"Wall Jump Off +50"**. **Neither was ported.** The approved stunt
matrix governs: **+200 is `wall_run_kill` — points ONLY for a kill
during a wall-run**; starting a wall-run and the wall jump pay
nothing.

**ANTI-FARM PROOF** (Cyrus-ordered assertion): 5 scripted
enter/exit cycles across all exit modes (stop, turn-away, wall
jump, time cap, slide) with no kill → **stunt score delta EXACTLY
0 (0 → 0), 0 stunt events, 0 shots fired**. Only the scripted
wall-run kill added points.

## 3. Over-the-shoulder camera — `level1/lobby_level.py` rig

True OTS: measured offset for a north-facing player =
**(right 1.15, up 2.40, back −6.50)** — camera over the right
shoulder. Shots resolve from the camera's aim ray through the
crosshair; a crosshair-centred guard was hit (hp 100 → 66 at
7.96 u).

Honest mechanics, stated plainly:
- The aim point is where the camera ray lands; if the ray passes a
  live target's **body segment** within the aim-assist radius
  (1.3 — the GDD §6 aim assist, sized to the shoulder parallax),
  the shot converges on the body point nearest the crosshair line.
- Cover is enforced from BOTH ends: a target hidden from the
  camera by a solid is never snapped to, and the bullet itself is
  cover-checked from the muzzle — a target the camera sees over
  low cover can still be unreachable (the shot stops on the
  cover). Floor-1's desk and column gates pass under this scheme
  (see regression below), and a design note is recorded in the
  Stage-2 report's own terms: the desk covers the lower body.
- **Wall-run camera tilt**: the rig rolls toward the wall side —
  measured **−15.0° on a left wall** (spec: left −15°, right +15°,
  lerped in/out), recovering to **−0.01°** after detach. The
  assertion (≥10° during a sustained run, ~0 after) passes.

**Regression found and fixed during this build:** the first OTS
version (shoulder 1.35, centre-point snap) cut boss-fight DPS —
the Act-3 boss survived and the full cycle failed twice. Diagnosis
was measured with a probe (centre-to-ray distance 1.25–1.35, at
the snap boundary). Final scheme (shoulder 1.15 + body-segment
snap): probe hits 16/19, boss falls in ~15.7 s, cycle green twice
in a row. No gate was weakened to get there — the level-1 cover
gates pass as scripted.

## 4. The fiction — GDD + intro card

- `GDD.md` §6b "The Protagonist — The Action Star (official
  fiction)": a professional stunt actor auditioning for the lead
  in NYC's biggest action film; every floor is a LIVE TAKE on a
  film set; the Director judges S/A/B/C; motivation = the perfect
  take; the approved look.
- `intro_card.py` (NEW) + wiring in `phase4/game_entry.py`: on
  START the slate appears BEFORE Floor 1 — title "THE ACTION
  STAR", the fiction in three short lines, "The Director is
  watching. Impress the Director. Earn your S.", "CLICK OR PRESS
  ANY KEY — ROLL CAMERAS". While it is up, the floor clock is
  paused via TimerManager's cutscene pause and the pipeline does
  not tick (proven: 40 card frames, 0 pipeline frames, take clock
  untouched by the hold); any key/click (or a 3 s auto-hold)
  dismisses it and the take begins. It re-shows on a second
  START. The existing programmatic cycle flow is unbroken (the
  full-cycle suite passes through it).

## 5. Regression battery (all after the final code)

| Suite | Result |
|---|---|
| Logic suite (`logic/`) | **104/104 PASS** |
| Level-1 gates (`level1/test_level1_smoke.py`) | **27/27 PASS** — Bullet-Time FPS windows, all 4 collision checks, elevator S_time identity intact |
| Character suite (`test_character.py`) | **40/40 PASS** (two consecutive runs) + intro **10/10** |
| Full pipeline (`test_full_pipeline.py`) | **30/30 PASS** |
| Full cycle (`test_full_cycle.py`) | **27/27 PASS, two consecutive runs** — F1 B 8,661 · F2 A 10,137 · F3 A 12,327 (boss defeated 15.7 s) · final card **S "Perfect Take" 30,975** on the real VictoryScreen |
| Phase-4 menu smoke | **23/23 PASS** (see note below) |
| Stage-3 smoke | **30/30 PASS** |
| HUD smoke | **13/13 PASS** |
| Audio math | **ALL PASS** |
| Save system | **PASS (exit 0)** |

Note (honest housekeeping): the menu smoke initially showed one
failure — "HIGH SCORES reads the best through SaveManager". Cause:
a STALE TEST DOUBLE — the final-wiring pass had tightened
HighScoresScreen to the real SaveManager contract (level numbers +
`best_rank` keys), and the menu test's FakeSaveManager still used
the old stage-string keys. The screen itself was already proven
against the REAL SaveManager (save-system suite + full-cycle
scores step). The double was corrected to the real contract; no
production code changed for it; the suite is 23/23.

## 6. Honest limits

- The model is code-built from boxes (v1, stated in its own
  docstring) — silhouette and poses read clearly; it is not a
  sculpted/rigged character asset.
- All proofs are headless under software rendering; FPS figures
  are sandbox floors, and feel (wall-run game feel, camera comfort)
  needs a human playtest on a real GPU.
- The aim assist (1.3 body-segment snap) is the GDD's own §6 aim
  assist made concrete for OTS parallax; no invisible magnetism
  beyond it — cover still blocks from both the camera and the
  muzzle, proven by the floor-1 gates.
- Windows .exe remains unbuilt (PyInstaller cannot cross-compile
  from Linux — see phase4/PACKAGING.md).

**STAGE: Character build COMPLETE — model, wall-run (1.8 s cap,
±15° tilt, wall jump, stick, anti-farm-proven scoring), OTS
camera, fiction + intro card; full regression green.
NEXT STEP: Cyrus's human playtest on a real machine (feel +
difficulty), then the Windows build on a Windows machine.**
