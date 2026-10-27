# Level 1 (Tower Lobby) — TEST REPORT

**Verdict: PASS — 27 checks, 0 failures**, reproduced on **two
consecutive full runs** of the scripted 3D autopilot under `xvfb-run`
(ursina 8.3.0 / Panda3D 1.10.16, real GL context, Mesa software
rendering).

- Primary run (all numbers below): **WIN in 30.38s** of the 90s
  target, 944 frames rendered in 30.42s wall time.
- Confirmation run: **WIN in 31.24s**, S_total 6,125, rank B,
  Gate 1 diff **+14.6%**, real bullet-dodge registered again.

The three acceptance gates issued by Cyrus are reported first, each
with its measured numbers.

---

## GATE 1 — FPS stability in Bullet Time: **PASS**

Average FPS measured in two 3.0s windows of the *same* scripted run
(player strafing at the arena under guard fire in both windows):

| Window | Avg FPS |
|---|---|
| Normal speed (time-scale 1.0, asserted every frame) | **33.3** |
| Bullet Time active (time-scale 0.3, asserted every frame) | **31.0** |
| Difference | **−7.0%** |

Severe-drop line: −35%. The switch to 0.3× costs almost nothing —
**no severe drop**. The confirmation run measured 27.8 → 31.8
(**+14.6%**).

*Caveat (stated once, per orders): these FPS values come from the
sandbox's software renderer (Xvfb + Mesa llvmpipe), not a GPU. The
gate measures the* relative *cost of the Bullet Time switch, which
is the property that matters here; absolute FPS on a real gaming
machine will be far higher and must be re-measured there.*

While Bullet Time was active the test also asserted, from live
state: world time-scale exactly **{0.3}** for the whole window,
energy charge draining **100 → 73** (≈10%/s GDD rate), and scale
restored to exactly **1.0** after switch-off.

## GATE 2 — Collision-box correctness (anti-clipping): **PASS** (4/4)

| Check | Result | Evidence |
|---|---|---|
| Player vs column | **PASS** | Pushing west into the marble column at (−8, 0): stopped at **x = −6.72**, column face at −7.20 (player radius 0.45 → resting clearance **0.034u**, never negative = no clip); max movement per frame after contact **0.004u** (hard stop, no grinding through). |
| Player vs reception desk | **PASS** | Pushing north into the desk: stopped at **z = −8.55**, desk south face at −8.10, min clearance **0.001u**, max movement per frame after contact **0.000u**. |
| Bullet vs column | **PASS** | 3/3 hitscan shots fired directly at the column registered impact **on `column_-8_+0` at 4.05u** from the muzzle; the guard standing directly behind it at ~11.0u was **unharmed (HP 100)**. |
| Bullet vs desk | **PASS** | 3/3 shots registered impact **on `reception_desk` at 4.09u**; the guard behind it at ~9.3u **unharmed (HP 100)**. Shots were aimed at the guard's lower body — the part the 1.15u-high desk actually covers (see honest note below). |

*Honest note on the desk geometry:* at chest height a shot **clears**
the 1.15u-high desk and hits the guard behind it — measured directly
in an earlier run (3 chest hits before the 4th, lower shot struck the
desk). That is real geometry, not a collision failure: a waist-high
desk covers the lower body only. The blocked-shot evidence above is
therefore taken against the covered body part.

## GATE 3 — Elevator trigger accuracy: **PASS**

The WIN fired when the autopilot entered the elevator goal zone, and
the final report card was produced by `logic/take_rating.py` from
the **live** HUD/logic state of that run. The test asserted, from
the run's own numbers:

- **S_time formula:** recorded **5,962** == max(0, (90 − 30.38) × 100)
  = **5,962** recomputed independently from the run's T_actual
  (30.38s). Exact match.
- **Total consistency:** S_total **6,212** == S_time 5,962 +
  stunt_base 250 × combo 1.0. Exact.
- **Rank consistency:** record says **B / "Good Take"**; the approved
  §7c rank table independently maps 6,212 → B / "Good Take". Match.
- **HUD dataset transferred without loss:** the final record carries
  outcome, reason, elapsed_s 30.38, target_s 90.0, **HP 51.0**,
  **bullet-time charge 77.1**, **stunt score 350**, stunt_base 250,
  combo 1.0, S_time, S_total, rank, title — all present, all live
  values.

### Final report card — verbatim from the passing run

```
=========== FINAL TAKE — LEVEL 1: TOWER LOBBY ===========
Outcome ....... WIN (Elevator reached)
Time .......... 30.38s / Target 90.00s
HP ............ 51.0%
Bullet Time ... 77.1% charge
Stunt Score ... 350 (base 250 x combo 1.0)
S_time ........ 5,962
S_total ....... 6,212
RANK .......... B — Good Take
===========================================================
```

Stunt base 250 = Air Takedown 150 + Bullet Dodge 50 × 2 (a second
dodge registered during the Gate-1 window while the elevator guard
fired at the strafing player in Bullet Time). The live HUD score
(350) applies each event's combo at the moment it happened, per
§7c; the Take Rating re-derives from base × final combo, also per
§7c — both numbers are the system's own, untruncated.

---

## Per-mechanic proof table (primary run)

| Mechanic | Result | Evidence |
|---|---|---|
| Movement + collision | PASS | Both push tests above; waypoint navigation crossed the lobby repeatedly without clipping (min clearances ≥ 0). |
| Shooting (hitscan + tracer) | PASS | Guard G1 killed with **8 shots / 8 tracers**; fire resolved against cover rays (see Gate 2). |
| Melee | PASS | Guard G2 killed in melee range; **`air_takedown` stunt registered** from the real kill. |
| Slide | PASS | Slide distance **6.68u** in 0.65s vs **4.88u** walking the same duration (slide is genuinely faster, decay curve applied). |
| Bullet Time (L-SHIFT) | PASS | Scale {0.3} asserted; drain 100 → 73; 5s cooldown honoured (an activation press inside the cooldown is refused — the test waits for the real activation before measuring); off restores 1.0. |
| Guard AI (×3) | PASS | Patrol → alert (sight + gunshot) → engage all observed live; guards fire **real projectiles** (travel + hit detection; a stationary player in the open takes ~11 hits in 8s under triple crossfire — measured in a side diagnostic). |
| Bullet Dodge | PASS | **Real dodge event**: guard bullet passed within the 1.7u dodge radius during Bullet Time, HP unchanged **72 → 72**, `bullet_dodge` +50 registered and shown on the HUD feed path. |
| Elevator WIN + rating | PASS | See Gate 3. |
| HUD wiring | PASS | HP / charge / time / score / combo
...[truncated 2573 chars]