# TEST REPORT — Action Star: NYC Siege 3D · Game-Logic Core (Stunt Score System)

- **Date:** 2026-10-27
- **Scope:** `logic/` — StuntManager, TimerManager, TakeRating. Engine-agnostic (no pygame/ursina imports); all time comes from injected clocks, so every number below is deterministic and reproducible.
- **QA law applied:** nothing in this report is claimed — it was run. `python3 logic/test_stunt_system.py` → **96/96 checks PASS, exit code 0**. Placeholder scan (TODO / FIXME / "Add logic here" / bare `pass` / `...` stubs) over all files: **clean**.

## Files

| File | Bytes | Role |
|---|---|---|
| `logic/stunt_manager.py` | 11629 | Stunt Score, variety combo multiplier, Multi-Kill Combo |
| `logic/timer_manager.py` | 6919 | Stage timer, S_time, best-time record |
| `logic/take_rating.py` | 4194 | Final Take Rating (Cyrus's approved formula + official table) |
| `logic/__init__.py` | 1241 | Package exports |
| `logic/test_stunt_system.py` | 21429 | This QA runner (deterministic, plain asserts + report) |
| `logic/TEST-REPORT.md` | — | This report |

## What the tests prove

- **Stunt Matrix lands exactly** (dodge 50 / slide 100 / air 150 / wall 200), and Cyrus's own `register_stunt` semantics: a new action type (absent from the last 3) raises the multiplier +0.5 *before* scoring; repeats never raise it; the sliding last-3 window is honoured; the multiplier caps at exactly ×5.0.
- **Combo reset** on player hit returns the multiplier to ×1.0 and keeps the banked score.
- **Multi-Kill Combo**: 3 kills spread over 6s pay nothing; kills at exactly 0.0/1.0/2.0s fire; a 3rd kill at 2.01s does not. In one 5-kill cluster the bonus escalates ×2 → ×3 → ×5 paying 950 + 1950 + 4100 (see interpretation note 1).
- **Timer**: S_time strictly decreases as elapsed grows; pause/resume spans are excluded; `finish()` freezes the clock; best time updates only when beaten; overtime S_time is 0.
- **Approved formula anchors**: 85s vs 120s target → **S_time = 3,500**; every rank is exercised through `rate()` under the official math (6000→B, 15000→S, 5000→C, 12100→A, 950→F), including proof the multiplier never touches S_time.
- **No interference**: stunt and timer managers share one clock in an interleaved stream and both states stay exact; the combined take grades 11500 + 150×2.0 = 11800 → A "Box Office Hit".

## Interpretation notes (where the spec needed a decision)

1. **Multi-Kill band reachability.** Paying the bonus once at the 3rd kill and "consuming" those kills would freeze every cluster at ×2 — the ×3/×5 bands in Cyrus's table would be dead code. Implemented instead as an **escalating entitlement**: each kill in the trailing 2.0s window is entitled to `points × (band − 1)`; when the band rises, only the unpaid difference is paid. No kill is ever paid twice, and a later separate cluster earns its own bonus.
2. **S_stunt is the raw base sum.** Per the approved formula, `rate()` takes the raw sum of stunt base points (`StuntManager.raw_base_total`, a property added for this) and the final combo multiplier — *not* the manager's live `current_score` (which applies the multiplier per event and adds Multi-Kill bonuses). `current_score` remains the live HUD meter; the Final Take Rating re-derives its stunt component exactly as the formula prescribes. Multi-Kill bonus points therefore do not enter S_total directly — they are the HUD/feedback reward. Flagged in case Cyrus wants them inside the rating too.
3. **Formula history.** Two interim variants were superseded the same day (×10 per second; then 1000 + 20×remaining). Only the final approved formula is implemented: `S_time = max(0, (T_target − T_actual) × 100)`, documented verbatim in `take_rating.py` as "Approved by Cyrus 2026-10-27".
4. **⚠️ One conflict to confirm.** Cyrus's earlier example said a total of **5,950 "must rate B"**, but his official table sets B at **≥ 6,000** (5,950 falls in C "Wrap Scene", 3,000–5,999). The table was implemented **verbatim** — 5,950 currently rates C. If the example was the intent, it is a one-line threshold change.
5. **Window boundary.** A kill exactly 2.0s after the first counts as inside the window (inclusive); 2.01s does not. The stunt component `int(S_stunt × M_combo)` truncates, matching Cyrus's own `int(points * multiplier)` style.

## Full test output (verbatim)

```
========================================================================
Action Star: NYC Siege 3D — logic core QA (deterministic)
========================================================================

--- Stunt Matrix ---
[PASS] matrix matches Cyrus's Stunt Matrix table — got {'bullet_dodge': 50, 'slide_shoot': 100, 'air_takedown': 150, 'wall_run_kill': 200}
[PASS] matrix bullet_dodge: first action scores int(50 x 1.5) — got added=75 mult=1.5
[PASS] matrix bullet_dodge: score banked — got 75
[PASS] matrix slide_shoot: first action scores int(100 x 1.5) — got added=150 mult=1.5
[PASS] matrix slide_shoot: score banked — got 150
[PASS] matrix air_takedown: first action scores int(150 x 1.5) — got added=225 mult=1.5
[PASS] matrix air_takedown: score banked — got 225
[PASS] matrix wall_run_kill: first action scores int(200 x 1.5) — got added=300 mult=1.5
[PASS] matrix wall_run_kill: score banked — got 300

--- Diversity multiplier ---
[PASS] first action bumps multiplier 1.0 -> 1.5 — got 1.5
[PASS] repeating the same action does not raise multiplier — got 1.5
[PASS] four distinct actions climb 1.5 / 2.0 / 2.5 / 3.0 — got [1.5, 2.0, 2.5, 3.0]
[PASS] action still inside last-3 window gives no bump — got 2.5
[PASS] brand-new action bumps again (x3.0) — got 3.0
[PASS] multiplier caps at exactly 5.0 — got 5.0
[PASS] multiplier never exceeds 5.0 — peak 5.0

--- Explicit points & validation ---
[PASS] register_stunt explicit 50 == matrix route (75 @ x1.5) — got (75, 1.5)
[PASS] points override works for an unlisted action (80 @ x2.0) — got (80, 2.0)
[PASS] unknown action without points raises ValueError
[PASS] negative points raise ValueError
[PASS] float points raise TypeError
[PASS] non-callable clock raises TypeError
[PASS] empty action name raises ValueError

--- Combo reset ---
[PASS] pre-reset state: multiplier 2.0, score 275 — got mult=2.0 score=275
[PASS] reset_combo returns multiplier to 1.0 — got 1.0
[PASS] reset_combo keeps the banked score — got 275

--- Multi-Kill escalation ---
[PASS] per-event returns incl. escalating bonuses — got [150, 300, 1450, 2450, 4400]
[PASS] final score after the 5-kill cluster — got 8750
[PASS] three bonus payments recorded (one per band rise) — got 3
[PASS] bonus bands escalate x2 -> x3 -> x5 — got [2.0, 3.0, 5.0]
[PASS] bonus points per payment — got [950, 1950, 4100]
[PASS] kills per window grow 3 -> 4 -> 5 — got [3, 4, 5]
[PASS] base award stored on the event excludes the bonus — got 500
[PASS] raw base total over the cluster (100+150+200+200+100 = 750) — got 750

--- Multi-Kill spread (no bonus) ---
[PASS] 3 kills spread over 6s trigger NO multi-kill bonus — got []
[PASS] spread-kill score is pure stunt points (950) — got 950

--- Multi-Kill window boundary ---
[PASS] kills at 0.0 / 1.0 / 2.0 are inside the 2.0s window -> bonus fires — bonuses=1 third=1450
[PASS] third kill at 2.01s falls outside -> no bonus — bonuses=0 third=500

--- Multi-Kill band table ---
[PASS] band(0 kills) == x1.0 — got x1.0
[PASS] band(1 kills) == x1.0 — got x1.0
[PASS] band(2 kills) == x1.0 — got x1.0
[PASS] band(3 kills) == x2.0 — got x2.0
[PASS] band(4 kills) == x3.0 — got x3.0
[PASS] band(5 kills) == x5.0 — got x5.0
[PASS] band(12 kills) == x5.0 — got x5.0

--- TimerManager ---
[PASS] elapsed is 0 before start
[PASS] S_time before start uses the full cap (180 x 100 = 18000) — got 18000
[PASS] elapsed 30 after advancing 30s — got 30.0
[PASS] remaining 150 — got 150.0
[PASS] S_time at 30s elapsed == 150 x 100 = 15000 — got 15000
[PASS] S_time decreases as elapsed grows (10500 < 15000) — got 10500
[PASS] paused span is excluded from elapsed (still 75) — got 75.0
[PASS] resume continues cleanly (80) — got 80.0
[PASS] finish returns the final elapsed (80) — got 80.0
[PASS] best_time recorded (80) — got 80.0
[PASS] elapsed stays frozen after finish
[PASS] S_time at rating time uses the frozen clock (10000) — got 10000
[PASS] a slower run does NOT overwrite the best time — got 80.0
[PASS] a faster run DOES update the best time — got 60.0
[PASS] start() twice raises RuntimeError
[PASS] pause() before start raises RuntimeError
[PASS] non-positive cap raises ValueError
[PASS] overtime remaining clamps to 0 — got 0.0
[PASS] overtime S_time is 0 (max(0, ...) — no base points) — got 0

--- S_time formula sanity (85/120) ---
[PASS] S_time at 85/120 == (120-85) x 100 == 3500 — got 3500
[PASS] S_time stays 3500 after finish (frozen) — got 3500
[PASS] a perfect instant finish would give 120 x 100 = 12000

--- TakeRating ---
[PASS] rank_for_total(0) == (F, 'Re-take Required') — got ('F', 'Re-take Required')
[PASS] rank_for_total(2999) == (F, 'Re-take Required') — got ('F', 'Re-take Required')
[PASS] rank_for_total(3000) == (C, 'Wrap Scene') — got ('C', 'Wrap Scene')
[PASS] rank_for_total(5999) == (C, 'Wrap Scene') — got ('C', 'Wrap Scene')
[PASS] rank_for_total(6000) == (B, 'Good Take') — got ('B', 'Good Take')
[PASS] rank_for_total(9999) == (B, 'Good Take') — got ('B', 'Good Take')
[PASS] rank_for_total(10000) == (A, 'Box Office Hit') — got ('A', 'Box Office Hit')
[PASS] rank_for_total(14999) == (A, 'Box Office Hit') — got ('A', 'Box Office Hit')
[PASS] rank_for_total(15000) == (S, 'Perfect Take') — got ('S', 'Perfect Take')
[PASS] rank_for_total(40000) == (S, 'Perfect Take') — got ('S', 'Perfect Take')
[PASS] rate: 3500 + 1000x2.5 = 6000 -> B 'Good Take' — got (6000, 'B', 'Good Take')
[PASS] rate: 3500 + 2300x5.0 = 15000 -> S 'Perfect Take' — got (15000, 'S', 'Perfect Take')
[PASS] rate: 3500 + 500x3.0 = 5000 -> C 'Wrap Scene' — got (5000, 'C', 'Wrap Scene')
[PASS] rate: 11800 + 150x2.0 = 12100 -> A 'Box Office Hit' — got (12100, 'A', 'Box Office Hit')
[PASS] rate: 0 + 950x1.0 = 950 -> F 'Re-take Required' — got (950, 'F', 'Re-take Required')
[PASS] multiplier never touches S_time (10000 + 0x5.0 stays 10000 -> A) — got (10000, 'A', 'Box Office Hit')
[PASS] evaluate breakdown: component 2500, total 6000, B 'Good Take' — got TakeResult(s_time=3500, stunt_base=1000, combo_multiplier=2.5, stunt_component=2500, total=6000, rank='B', title='Good Take')
[PASS] stunt component truncates like the house int() style (687) — got TakeResult(s_time=0, stunt_base=275, combo_multiplier=2.5, stunt_component=687, total=687, rank='F', title='Re-take Required')
[PASS] negative s_time raises ValueError
[PASS] float s_stunt raises TypeError
[PASS] zero multiplier raises ValueError

--- Simultaneous stunt+timer ---
[PASS] interleaved: dodge scores 75 @ x1.5 — got 75
[PASS] interleaved: slide_shoot scores 200 @ x2.0 — got 200
[PASS] timer tracks the shared clock (2.0s) — got 2.0
[PASS] S_time at 2s elapsed == 118 x 100 = 11800 — got 11800
[PASS] stunt events do not move the timer (5.0s) — got 5.0
[PASS] timer does not touch the live stunt score (275) — got 275
[PASS] raw stunt base sum for the rating formula (50 + 100 = 150) — got 150
[PASS] combined take: 11500 + 150x2.0 = 11800 -> A 'Box Office Hit' — got (11800, 'A', 'Box Office Hit')

========================================================================
SUMMARY: 96/96 checks passed, 0 failed, 0 sections crashed
VERDICT: ALL CHECKS PASSED
```

## Verdict

**PASS — 96/96 checks, exit 0.** The logic core is ready to be wired into the engine layer (HUD reads: `TimerManager.time_bonus()` for S_time, `StuntManager.current_score` / `combo_multiplier` for the live meter, `take_rating.rate(...)` at stage end).

---

## Addendum — Stage-3 stunt actions (2026-10-27)

Cyrus's Stage-3 order added two moves to the Stunt Matrix in
`stunt_manager.py`, registered through the same `register()` path and
combo math as every Stage-1 action:

| Action | Base points | Meaning |
|---|---|---|
| `defenestration` | **500** | Throwing an enemy out of the penthouse window (highest-value move in the game) |
| `shield_bypass` | **250** | Defeating a shielded Enforcer via slide-under / flank |

Both were also added to `KILL_ACTIONS` (each defeats an enemy, so both
join Multi-Kill Combo windows like the Stage-1 kills). No existing
behaviour changed: the original four matrix values are untouched.

Test changes in `test_stunt_system.py`:
- the matrix-equality check now asserts the full six-action table;
- a new "Stage-3 stunt actions" section asserts the 500/250 matrix
  values and that `register("defenestration")` banks 750 and
  `register("shield_bypass")` banks 375 on a fresh manager (500/250
  base × 1.5 first-action combo), with the base recorded exactly.

Re-run after the change (2026-10-27):

```
SUMMARY: 104/104 checks passed, 0 failed, 0 sections crashed
VERDICT: ALL CHECKS PASSED
```

(96 original checks preserved and green, +4 in the matrix loop for the
two new actions, +4 in the new Stage-3 section.)
