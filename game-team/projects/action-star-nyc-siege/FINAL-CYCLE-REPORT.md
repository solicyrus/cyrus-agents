# FINAL-CYCLE-REPORT — Action Star: NYC Siege 3D

**Scope:** Cyrus's two final-wiring orders (2026-10-27) — (1) the
applied time-bank bonus capped at **+30 s**, and (2) the main menu's
START wired to the real three-floor pipeline, proven by a full-cycle
test.
**Verdict: PASS — 27/27 checks on TWO consecutive full-cycle runs**
(exit code 0 both times; Cyrus's verification rule — no single lucky
sample). Sandbox software rendering under Xvfb — FPS figures are a
floor for playability, not a GPU prediction.

Test: `test_full_cycle.py` (project root). Each execution boots the
REAL packaged entry (`phase4/game_entry.py`) in one process against a
throwaway HOME, probes STAGE SELECT, presses START GAME, plays all
three floors with the proven scripted autopilot (injected through
`game_entry.set_input_provider`, the same seam `pump()` feeds from
the keyboard in live play), and walks the cycle back to the menu.

Run it: `xvfb-run -a /tmp/ursina-venv/bin/python test_full_cycle.py`

---

## Order 1 — time-bank cap +30 s

Rule (in `pipeline_state.py`, `RunState.effective_target`):
`effective_target = base_target + min(banked_seconds, 30.0)`
(`BANK_BONUS_CAP_S = 30.0`). Accrual is unchanged — remaining is
still computed against each floor's effective cap and accrues in
full; only the applied bonus is capped.

Unit evidence (asserted in both test files):
- banked **84.3** → next floor targets **105.0 / 135.0** (base + 30.0
  exactly, NOT +84.3);
- banked **12.0** → target **87.0** (base + 12, under the cap);
- through a real settle: 84.3 s remaining accrues as 84.3 in the run
  state, next floor's cap is 105.0.

Live evidence (both cycle runs): the Lobby banked ~84 s out; Floor
2's cap was **105.00 = 75 + min(84.07, 30)** (run 2: min(83.92, 30));
the Data Center banked ~98 s out; Floor 3's cap was **135.00 =
105 + min(98.41, 30)** (run 2: min(98.57, 30)). The elevator panel
prints the applied figure honestly: "Banked +30.0s to the next floor
(applied bonus, cap +30s)".

The pipeline suite (`test_full_pipeline.py`) was re-run under the
cap with its banking expectations updated: **PASS 30/30, exit 0**
(final S_total 30,822, rank S — "Perfect Take"). TEST-REPORT.md
carries the addendum; its earlier uncapped runs (caps 159.29 /
258.29) stand as history.

## Order 2 — START → FullGamePipeline wiring

`phase4/game_entry.py` (rewritten seam, same shell):
- One shared `SaveManager` for the whole shell; the pipeline's
  `SaveBridge` is bound to it, so run records are the records the
  menus read.
- `launch_stage(stage_id)` constructs the real `FullGamePipeline`
  with the entry's real `VictoryScreen`: START GAME = the full chain
  from Floor 1; a LevelSelectMenu choice starts at that floor (fresh
  RunState; a locked floor would be refused by the pipeline through
  the shared manager).
- STAGE SELECT opens the real `LevelSelectMenu` (via a show()/hide()
  host adapter — the menu owns loose entities, the seam expects a
  root); cards refresh from the shared manager on every open.
- VictoryScreen RE-TAKE restarts the run from its starting floor;
  BACK TO MENU disposes the pipeline and returns control to the live
  `MainMenuState`. Frame driving is unified in `game_entry.pump(dt)`:
  keyboard/mouse in live play, a registered input provider in tests.
  Bullet Time drives `SoundManager.set_bullet_time` while a floor is
  live.

**Latent bug found and fixed on the way** (`phase4/game_ui_screens.py`):
`HighScoresScreen` called `SaveManager.get_level_record()` with a
stage-id STRING (the real API takes a level number — it would have
raised ValueError on the first HIGH SCORES open against the real
save system) and `_record_fields` still normalized the pre-landing
placeholder keys, so ranks would have rendered blank. Both tightened
to the real API/keys (the exact fix the Phase-4 report flagged);
proven live by the cycle's scores check below, which reads this
run's real records off the screen.

## The cycle, per run

### Run 1 — PASS 27/27 (1,265 frames, 37.08 s, avg 34.1 fps)

| Segment | Frames | Wall | FPS |
|---|---|---|---|
| menu (boot + stage-select probe) | 75 | 2.88 s | 26.1 |
| floor1 Lobby | 199 | 5.68 s | 35.1 |
| transition1 (elevator) | 123 | 3.17 s | 38.8 |
| floor2 Data Center | 213 | 6.60 s | 32.2 |
| transition2 (elevator) | 120 | 3.19 s | 37.6 |
| floor3 Penthouse + boss | 399 | 12.44 s | 32.1 |
| victory_card | 46 | 0.93 s | 49.4 |

Chain: Lobby WIN 5.93 s — floor total **8,632, rank B**, banked out
84.07 → Data Center cap 105.00, WIN 6.59 s — **10,065, rank A**,
banked out 98.41 → Penthouse cap 135.00, WIN 12.43 s (boss defeated)
— **12,407, rank A**. Stunt raw chain 0 → 150 → 300 → 450 (never
reset). Final card (verbatim from the real VictoryScreen):

```
TAKE COMPLETE — NYC SIEGE — FULL RUN
RANK S — Perfect Take
S_time ......... 30,504
S_stunt ........ 450  x 1.5 combo = 450
S_total ........ 30,954
Time 24.9s / Target 330s
Combo peak x1.5
Air Takedown x3
```

### Run 2 — PASS 27/27 (1,269 frames, 37.70 s, avg 33.7 fps)

Segments (frames / fps): menu 75 / 24.9 · floor1 198 / 34.1 ·
transition1 119 / 37.4 · floor2 230 / 35.7 · transition2 118 / 35.7 ·
floor3 393 / 31.3 · victory_card 46 / 44.8.
Chain: Lobby **8,617 B** (6.08 s) → cap 105.00 → Data Center
**10,082 A** (6.43 s) → cap 135.00 → Penthouse **12,394 A** (12.55 s,
boss defeated). Final card: S_time 30,493 + 450 = **S_total 30,943 —
rank S, "Perfect Take"** (independently recomputed in-test: equal).

### Checks asserted in each run (27)

Cap units ×4 · boot menu up · stage↔floor wiring map · level select
shows + locked card 3 inert (activate returns None, no pipeline) ·
level-select Back returns to menu · START begins pipeline at Floor 1
(menu `last_action == "start"`) · Floor 2 cap == 75 + min(bank, 30) ·
Floor 3 cap == 105 + min(bank, 30) · transitions after Floors 1 and 2
rendered (>30 frames; 118–123 observed) carrying the floors' real
rank/S_time · three floors settled, all WIN · boss defeated · stunt
continuity · final card on the real VictoryScreen (rank/S_total ==
pipeline's, arithmetic recomputed) · BACK TO MENU live (pipeline
disposed, menu active, card hidden) · HIGH SCORES opens and shows
THIS run's records (no "No takes yet") · scores Back returns to menu
· temp `user_progress.json` holds all three floors' records from
this run (score/time/rank == the floors' own numbers) with
`unlocked_levels == [1, 2, 3]`.

## Honest notes / remaining seams

- **Card label cosmetics:** the VictoryScreen's breakdown line
  labels the stunt component with the run's combo PEAK ("450 x 1.5
  combo = 450") while the component itself is computed with the
  FINAL combo (1.0) per the approved formula — the totals add up
  (30,504 + 450 = 30,954) and match the pipeline record exactly;
  only the "x 1.5" label is the peak, not the applied multiplier.
  Display wording is the screen's shipped format; flagged, not
  silently changed.
- **Unverifiable here (unchanged):** human control/camera feel, real
  GPU FPS and visuals, and audio by ear (no audio device in the
  sandbox; the sound pipeline is file/math-verified from Phase 4).
- **Windows .exe still pending a Windows machine** — PyInstaller
  cannot cross-compile from this Linux sandbox; `phase4/PACKAGING.md`
  carries the one-command Windows build with the same spec. The
  Linux build was proven in Phase 4; this wiring changes no
  packaging inputs beyond `game_entry.py` itself, which is the
  spec's entry module.
- The two cycle runs wrote their saves to throwaway HOMEs
  (`/tmp/actionstar-cycle-*`); the developer profile's real
  `~/.actionstar/user_progress.json` was not touched by the cycle
  test (the pipeline-suite re-run used it, as before).

**STAGE:** Final wiring complete — the game boots to its menu and
plays the full tower from it, with records, unlocks and the capped
time bank all proven in the loop.
**NEXT STEP:** a human play session on a real machine (feel, GPU
FPS, audio) and the Windows .exe build on a Windows machine.
