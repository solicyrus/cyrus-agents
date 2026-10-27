# FINAL SYSTEM AUDIT — Action Star: NYC Siege 3D

**Date:** 2026-10-27 · **Role:** QA Destroyer — independent re-verification.
Nothing in this report is copied from earlier reports: every check below was
re-executed or re-inspected by the auditor in this pass.

**Environment:** system python3 (3.12) for static/logic/audio checks;
`/tmp/ursina-venv` (Ursina 8.3.0 / Panda3D 1.10.16) + `xvfb-run` for engine
runs. All FPS figures are sandbox software rendering — a floor for
playability, not a GPU prediction.

**Overall verdict: GREEN — system ready for Cyrus's human test tonight.**
No blockers. Two honest packaging notes and one known cosmetic label wart
are recorded in §4/§2 — none affects the math, the chain, or playability.

---

## §1 — Zero dangling code scan — ✅ GREEN

Scope: all **44** `.py` files in the project (root, `logic/`, `hud/`,
`level1/`, `stage3/`, `phase4/`). (`game_creator_agents/` is not inside
this project directory — it lives at the game-team root — so it is outside
this audit's stated scope.) All 44 files parse cleanly (AST walk, no
syntax errors).

| Scan | Result |
|---|---|
| `TODO` / `FIXME` / `XXX` / `HACK` markers | **0** |
| `NotImplementedError` raises | **0** |
| Empty function bodies (docstring / `pass` / `...` only) | **0** |
| Empty class bodies | **0** |
| Placeholder strings ("not implemented", "coming soon", lorem, "add logic here"…) | **0 in shipped code** — the only hits are the word "placeholders" inside `prototype3d.py`'s docstring *asserting the prototype has none*, and test-double class names (`PlayerStub`, `_HudStub`) in test files, which are real working test doubles, not placeholders |

**`pass` inventory — 8 occurrences, every one inspected in context:**

| # | Location | Context | Verdict |
|---|---|---|---|
| 1 | `character_model.py:184` | `if state == "IDLE": pass` in the pose dispatcher, immediately after `_reset_pose_transforms()` ran — IDLE *is* the reset pose, so "no extra offsets" is the correct, complete behavior | Legitimate (intentional no-op branch) |
| 2 | `full_game_pipeline.py:372` | `except Exception: pass` guarding `destroy(self.root)` in `dispose()` | Legitimate (teardown guard) |
| 3 | `full_game_pipeline.py:673` | same guard in the floor scene teardown destroy loop | Legitimate (teardown guard) |
| 4 | `full_game_pipeline.py:911` | same guard around the optional mouse-velocity probe in the input provider (if the API is absent, aim simply doesn't update that frame) | Legitimate (defensive probe) |
| 5 | `level1/main.py:229` | same mouse-velocity probe guard | Legitimate (defensive probe) |
| 6 | `phase4/game_entry.py:298` | same mouse-velocity probe guard | Legitimate (defensive probe) |
| 7 | `save_system.py:247` | `except OSError: pass` while unlinking the temp file after a failed save — the original error is **re-raised** on the next line, not swallowed | Legitimate (best-effort cleanup) |
| 8 | `test_full_pipeline.py:244` | teardown `destroy()` guard in a test file | Legitimate (test teardown) |

No `pass` anywhere is an empty function/class body or a placeholder for
unwritten logic. **Claim verified: 100% clean, with the 8 itemized
legitimate exceptions above.**

*Housekeeping note (not a defect):* `phase4/__pycache__/` still holds
bytecode for the deleted `scores_store.py` / `test_scores_store.py`. No
`.py` source exists and a project-wide grep finds **zero** references to
`scores_store` — the `.pyc` files are inert leftovers.

---

## §2 — Full chain re-run (menu → 3 floors → records → card → menu) — ✅ GREEN

`test_full_cycle.py` re-run fresh, **two consecutive executions**, real
packaged entry (`phase4.game_entry`), throwaway HOME per run:

| | Run 1 | Run 2 |
|---|---|---|
| Verdict | **PASS 27/27, exit 0** | **PASS 27/27, exit 0** |
| Frames / avg FPS | 1,265 frames (segment FPS in log) | — (log retained) |
| Floors | Lobby B 8,650 · Data Center A 10,069 · Penthouse A 12,224 | Lobby B 8,616 · Data Center A 10,114 · Penthouse A 12,298 |
| Elevator transitions | rendered with the finished floors' real stats | rendered |

Time-bank cap (Cyrus's +30 s rule) verified live in Run 1 from the
pipeline's own settle lines: Floor 2 effective target **105.0 = 75 +
min(84.3, 30)**; Floor 3 effective target **135.0 = 105 + min(98.5, 30)**.

**Verbatim final card — Run 1:**
```
TAKE COMPLETE — NYC SIEGE — FULL RUN
RANK S — Perfect Take
S_time ......... 30,093
S_stunt ........ 700  x 1.5 combo = 700
S_total ........ 30,793
Time 29.0s / Target 330s
Combo peak x1.5
Air Takedown x3
Bullet Dodge x5
```

**Verbatim final card — Run 2:**
```
TAKE COMPLETE — NYC SIEGE — FULL RUN
RANK S — Perfect Take
S_time ......... 30,178
S_stunt ........ 700  x 1.5 combo = 700
S_total ........ 30,878
Time 28.2s / Target 330s
Combo peak x1.5
Air Takedown x3
Bullet Dodge x5
```

**`user_progress.json` after Run 1** (that run's own temp HOME):
```json
{
    "unlocked_levels": [1, 2, 3],
    "levels_data": {
        "level_1": {"title": "NYC Tower Lobby",      "best_score": 8650,  "best_time": 5.74,  "best_rank": "B"},
        "level_2": {"title": "Data Center",         "best_score": 10069, "best_time": 6.55,  "best_rank": "A"},
        "level_3": {"title": "Penthouse & Helipad", "best_score": 12224, "best_time": 16.75, "best_rank": "A"}
    }
}
```

**`user_progress.json` after Run 2:**
```json
{
    "unlocked_levels": [1, 2, 3],
    "levels_data": {
        "level_1": {"title": "NYC Tower Lobby",      "best_score": 8616,  "best_time": 6.09,  "best_rank": "B"},
        "level_2": {"title": "Data Center",         "best_score": 10114, "best_time": 6.1,   "best_rank": "A"},
        "level_3": {"title": "Penthouse & Helipad", "best_score": 12298, "best_time": 16.01, "best_rank": "A"}
    }
}
```
Each run's file holds exactly that run's floor numbers — the saves are
provably written by the run itself, and BACK TO MENU returned to a live,
responsive menu in both runs (HIGH SCORES opened showing the run's
records).

*Known cosmetic wart (not a math defect):* the card line `S_stunt 700 x
1.5 combo = 700` prints the combo **peak** (×1.5) in the label while the
formula correctly applies the **final** combo (×1.0) — 700 × 1.0 = 700.
The totals are exact (see the independent recomputation in §3). Only the
label wording is loose; the wiring pass had already flagged it.

---

## §3 — Module audits — ✅ GREEN (all four)

### 3a. StuntManager & anti-cheat — ✅ GREEN
- Logic suite re-run: **104/104 PASS, exit 0**.
- Anti-farm re-probe (character suite, re-run): 5 wall-run enter/exit
  cycles (stop / away / jump / cap / slide exits) with no kill →
  **`antifarm_score_delta_exactly_zero: OK score 0 -> 0 (delta 0),
  events=0, shots=0`** — no points for entering, exiting, or
  wall-jumping. One wall-run kill → exactly one event
  `('wall_run_kill', 200)`, awarded 300 at ×1.5, independently
  recomputed inside the test to the same 300.
- Structural confirmation: in `level1/player_controller_3d.py`,
  `stunt.register(...)` is called **only** at kill sites (`slide_shoot`
  L607, `wall_run_kill` L610/L677, `air_takedown` L682). No register
  call exists on any wall-run start/attach path.
- Auditor's own independent probe (fresh code, no suite reuse):
  matrix `wall_run_kill == 200`; one registration →
  `raw_base_total == 200` exactly; `rate(3500, 200, 2.0) = (3900, 'C',
  'Wrap Scene')` matches the hand computation
  (3500 + 200×2.0 = 3900); rank-table boundaries 8/8 match Cyrus's
  approved table (15000 S / 10000 A / 6000 B / 3000 C / 2999 F).
- **Independent S_total recomputation for both cycle runs**, from each
  run's own per-floor settle lines:
  - Run 1: S_time 8,425 + 9,844 + 11,824 = **30,093**; raw stunt
    150+150+400 = **700**; `rate(30093, 700, 1.0)` = **(30,793, 'S',
    'Perfect Take')** == the card. ✅
  - Run 2: S_time 8,391 + 9,889 + 11,898 = **30,178**; raw stunt
    **700**; `rate(30178, 700, 1.0)` = **(30,878, 'S', 'Perfect
    Take')** == the card. ✅

### 3b. SoundManager (Bullet-Time pitch shift) — ✅ GREEN
Audio-math suite re-run (system python, WAV decode + FFT):
**ALL PASS** — all 20 WAVs (10 assets + 10 Bullet-Time variants) decode
as sane mono 16-bit PCM; every variant's duration ratio is exactly
**2.500×**; a known 440 Hz tone's 0.4× variant measures **176.0 Hz** by
FFT and lasts **2.50 s vs 1.00 s**. The 0.4× slow-motion pitch drop is
numerically real.
*Limit (environmental, unchanged):* this sandbox has no audio device
(NullAudioManager) — the shift is proven by measurement, not by ear.

### 3c. SaveManager — ✅ GREEN
Suite re-run in full: **15/15 logic checks** (system python) + **8/8 UI
checks** (venv/xvfb; 23 PROOF checks OK total, exit 0 both ways).
Verified behaviors: fresh profile → only Level 1 unlocked; pass (A)
unlocks the next level, chain to [1,2,3]; an F result records the score
but does **not** unlock; a lower score never overwrites the best record;
corrupt JSON → fresh defaults with no crash; reload from disk persists
identically; no Level 4 ever; locked level-select card is fully inert,
unlocked cards fire their callbacks. The two cycle runs (§2) additionally
prove the live wiring end-to-end.

### 3d. HUDManager — ✅ GREEN
- HUD smoke re-run: **13/13 PASS** (228 frames; HP text tracks state;
  Bullet-Time `⚡ READY (L-SHIFT)` state correct; feed pool spawns and
  expires cleanly).
- **UI-space separation — mechanism verified by code inspection:**
  `hud/hud_manager.py:93` sets `self._ui = camera.ui` and every HUD
  entity/text is created with `parent=self._ui`. Ursina renders
  `camera.ui` children in screen space, structurally outside the 3D
  scene graph — the HUD cannot be occluded by or interfere with world
  geometry.
- Boss bar (`stage3/boss_hud.py`, all elements `parent=camera.ui`):
  behavior re-proven in the stage3 re-run (**30/30 PASS**): hidden
  before the fight → shows `1200 / 1200 HP` (fraction 1.000) → tracks
  scripted damage to `700 / 1200 HP` (fraction 0.583, "PHASE 2" label)
  → hides when the boss dies; live during the boss + 3-enemies FPS
  check (25.2 FPS, software rendering).

*(Also re-run in this pass: character suite **40/40 PASS** — model,
7 poses, wall-run 1.8 s cap / stick gap 0.350 / camera roll −15.0°, OTS
camera, intro card.)*

---

## §4 — Packaging check — ✅ GREEN by inspection, with two honest notes

- **Relative addressing verified:** `phase4/assets.py` resolves assets
  via `sys._MEIPASS` when frozen, module-relative otherwise; user data
  goes to the writable `~/.action-star-nyc-siege/`, never the bundle.
  `build_executable.py` derives every path from `__file__`. A grep over
  all 44 `.py` files finds **zero** hardcoded absolute asset paths
  (no `/home/…`, `/tmp/…`, or `C:\…` literals).
- **Spec completeness (`phase4/main.spec`):** bundles `phase4/assets`
  (incl. `bullet_time/` variants + manifest), Ursina and Panda3D data
  files, and the Panda3D runtime plugins for **both** `.so` and `.dll`;
  hidden imports cover the phase4 + logic + hud packages. The remaining
  packages (`level1`, `stage3`, `save_system`, `level_select`,
  `pipeline_state`, `full_game_pipeline`, `character_model`,
  `intro_card`) are reached from the entry point by plain static
  imports — verified there is **no** `importlib` / `__import__`
  anywhere in the project, so PyInstaller's static analysis includes
  them all.
- **PACKAGING.md ↔ spec consistency:** the documented Windows flow
  (fresh clone → venv → `pip install ursina numpy pyinstaller` →
  `generate_audio_assets.py` → `build_executable.py`) produces
  `dist\ActionStarNYCSiege\ActionStarNYCSiege.exe`, exactly matching
  the spec's `name="ActionStarNYCSiege"` one-dir COLLECT. One command
  chain, correct output name/path.

**Honest notes (neither blocks tonight's human test, which runs from
source / a fresh build):**
1. **The previously built Linux dist artifact is not on disk at audit
   time.** Searched the project, the workspace, and /tmp: no
   `dist/ActionStarNYCSiege` exists now. The 2026-10-27 build + frozen
   smoke-run proof stands documented in `phase4/TEST-REPORT.md` and
   PACKAGING.md, but the artifact itself could not be re-inspected.
2. **`main.spec` is unchanged since that build** (so, per audit
   instructions, the build was not re-run; PyInstaller is also not
   installed in the sandbox venv at audit time) — **but**
   `game_entry.py`'s import graph grew after the build (final wiring +
   character/intro). Static analysis covers the new imports (no dynamic
   imports exist), yet the frozen binary has not been smoke-run against
   the *current* tree. Recommendation: on the Windows machine, follow
   PACKAGING.md exactly (it builds from a fresh clone of the current
   tree) and run the built .exe once before distributing it.

---

## Closing verdict

**✅ SYSTEM READY for Cyrus's human test tonight.** Every checklist
item was independently re-executed or re-inspected in this pass:
44-file clean scan, two consecutive full-cycle runs (27/27 each) with
verbatim S-rank cards and per-run save files, logic 104/104,
anti-farm delta exactly 0, S_total recomputed by hand for both runs,
audio pitch shift proven by FFT (440 → 176 Hz), save system 23/23,
HUD 13/13 in UI space with the boss bar proven, packaging consistent
and path-clean.

Remaining items that no sandbox audit can settle (unchanged,
environmental): human control feel and difficulty, real-GPU FPS and
visuals, audio by ear — and the Windows .exe itself, to be produced on
a Windows machine via PACKAGING.md.
