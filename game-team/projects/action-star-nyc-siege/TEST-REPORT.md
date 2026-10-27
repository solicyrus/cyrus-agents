# TEST-REPORT — Full Game Pipeline (Action Star: NYC Siege 3D)

**Integration build:** `full_game_pipeline.py` + `pipeline_state.py`, QA:
`test_full_pipeline.py` (this folder, project root).
**Verdict: PASS — 27/27 checks, twice in a row** (two full end-to-end
runs, exit code 0 both times), plus 3 supplementary level-select
checks. Sandbox software rendering under Xvfb — FPS figures are not a
GPU prediction.

Run it: `xvfb-run -a /tmp/ursina-venv/bin/python test_full_pipeline.py`

---

## What was built

| File | Size | Role |
|---|---|---|
| `full_game_pipeline.py` | 39,097 B / 926 lines | FloorSession assembly for all three floors, enemy target adapters, the `ElevatorTransition` scene state, the `FullGamePipeline` driver, standalone human entry point |
| `pipeline_state.py` | 13,397 B / 316 lines | `RunState` (shared StuntManager, HP, banked time, floor records), heal-by-rank v1, `SaveBridge` to save_system |
| `test_full_pipeline.py` | 31,977 B / 743 lines | Pre-flight unit checks + the scripted-autopilot full run with chain assertions |

Zero placeholders: every function is complete; the standalone entry
(`python full_game_pipeline.py`) plays the full chain with keyboard/
mouse using the same input builder pattern as level1/main.py.

## Chain rules, as implemented

1. **One StuntManager** per run (`RunState.stunt`), wired into every
   floor's PlayerController and BulletManager; score/combo/recent-
   action chain never reset between floors (its clock rebinds to the
   active floor's TimerManager).
2. **Time banking:** floor cap = base (90 / 75 / 105) + previous
   floor's remaining (`max(0, effective cap − actual)`), via
   `TimerManager.remaining`. Unspent banked seconds bank again — the
   rule as specified; see "Design consequence" under Seams.
3. **Heal by rank (v1):** floor take rated by `take_rating.evaluate`
   on the floor's own S_time + stunt base gained that floor; heal
   S → 100%, A → +60, B → +40, C → +25 (cap 100). F (or a lost floor)
   stops the chain: no heal, no banking, no advance.
4. **Final card:** `S_total = Σ floor S_time + (total raw stunt base ×
   final combo)` via `take_rating.evaluate`, delivered to phase4's
   real `VictoryScreen.show_result(result, run_record)` and kept as
   `pipeline.final_record` / `final_run_record`.
5. **Elevator transition:** `ElevatorTransition.show(record)` renders
   doors + a stats panel driven by the floor's real FloorRecord
   (time vs target, banked seconds, floor S_time, stunt gained, floor
   rank, heal applied) for 3.0 s between floors.
6. **Save wiring:** after each floor's take is rated,
   `SaveManager.save_stage_result(level_num, floor S_total, actual
   time, rank)` fires through `SaveBridge`. Starting floor is a
   constructor argument (level-select): fresh RunState above floor 1,
   per-floor saves still fire, locked floors refuse when the save
   system reports them locked.

## Per-assertion results (run 4 — the primary evidence run)

Pre-flight unit checks (deterministic, fake clocks):

| Check | Result | Evidence |
|---|---|---|
| unit_heal_S/A/B/C/F (6 checks) | OK | S: 37→100 (+63); A: 30→90 (+60), 80→100 (+20 cap); B: 30→70; C: 30→55; F: +0 |
| unit_settle_floor_math | OK | synthetic 90 s floor finished at 30 s: S_time 6000, banked 60.0, stunt +100 → total 6150, rank B, heal +40 (50→90), next cap 75+60=135 |
| unit_failed_floor_stops_chain | OK | lost floor → rank F, chain_failed, HP/bank untouched |
| unit_enforcer_frontal_blocked | OK | frontal shot "blocked", HP 850 intact, blocked_shots=1 |
| unit_enforcer_flank_kill_shield_bypass_once | OK | died on the 17th flank shot; events == ["shield_bypass"] exactly once; raw base 250 |
| unit_marksman_adapter_damage_and_death | OK | 34 dmg ×5 → [F,F,F,F,True], alive False, state "down" |
| unit_boss_adapter_passthrough | OK | boss HP 1200→1166 through BossEnemy's own method |

Integrated run checks:

| Check | Result | Evidence |
|---|---|---|
| chain_reached_final_phase | OK | phase=final |
| three_floors_settled | OK | [(1, WIN, B), (2, WIN, S), (3, WIN, S)] |
| transition_after_floor1 | OK | rendered 129 frames; title "ELEVATOR — FLOOR 1 COMPLETE: LOBBY"; panel carried rank B + S_time 8,428 |
| transition_after_floor2 | OK | rendered 123 frames; title "…FLOOR 2 COMPLETE: DATA CENTER"; rank S on panel |
| stunt_manager_single_instance | OK | one object id across all three floors |
| stunt_continuity | OK | floor 2 starts at score 225 / raw 150 = floor 1's end; floor 3 starts at raw 300 = floor 2's end; never zeroed |
| floor2_target_banked | OK | cap 159.29 = 75 + 84.29 banked |
| floor3_target_banked | OK | cap 258.29 = 105 + 153.29 banked |
| heal_floor1_exact | OK | rank B: HP 93 +7 (table +40, capped) → 100; floor 2 started at exactly 100 |
| heal_floor2_exact | OK | rank S at full HP: +0 → 100; floor 3 started at 100 (no-op heal — see Honest notes) |
| boss_defeated | OK | boss_defeated=True, outcome WIN ("Syndicate Boss defeated") |
| final_card_arithmetic | OK | S_total 48,843 = S_time 48,393 + 450 × 1.0, recomputed independently via take_rating |
| final_rank_title_present | OK | S — "Perfect Take" |
| victory_screen_shown | OK | real phase4 VictoryScreen visible, outcome=victory, screen rank S = pipeline rank S |
| save_calls_per_floor | OK | 3 calls, delivered=True, args = each floor's (number, S_total, time, rank) |

Supplementary level-select checks (separate headless script):
locked floor 2 (stub bridge reporting locked) → `ValueError` refusal;
start at floor 3 against the REAL save → fresh state (cap 105.0, stunt
0, HP 100); start at floor 2 → cap 75.0, fresh.

## Full chain log (run 4)

```
FLOOR 1 Lobby: WIN (Elevator reached) | time 5.71s / 90.0s (base 90 + banked 0.0)
  | S_time 8,428 | stunt +150 base (run 150, combo x1.5) | floor total 8,653
  RANK B (Good Take) | HP 93 +7 -> 100 | banked out 84.3s | save delivered=True
  | fps 37.2
FLOOR 2 Data Center: WIN (Elevator reached) | time 5.99s / 159.3s (base 75 + banked 84.3)
  | S_time 15,329 | stunt +150 base (run 300, combo x1.5) | floor total 15,554
  RANK S (Perfect Take) | HP 100 +0 -> 100 | banked out 153.3s | save delivered=True
  | fps 42.6
FLOOR 3 Penthouse: WIN (Syndicate Boss defeated) | time 11.93s / 258.3s (base 105 + banked 153.3)
  | S_time 24,636 | stunt +150 base (run 450, combo x1.0) | floor total 24,786
  RANK S (Perfect Take) | HP 30 +70 -> 100 | banked out 246.4s | boss_defeated=True
  | save delivered=True | fps 35.6
FINAL CARD: outcome COMPLETE | S_time total 48,393 | stunt base 450 x combo 1.0
  = 450 | S_total 48,843 | RANK S — Perfect Take | save_system_present=True
PROOF full_pipeline PASS: 27 checks, 0 failures — EXIT=0
```

Confirmation run 5 (same test, immediately after): **PASS 27/27,
EXIT=0** — floors B / S / S, S_total 48,708 (S_time 48,258 + 450 × 1.0),
transitions 125 / 122 frames, FPS 31.8 / 43.4 / 35.6. The small
numeric drift between runs is frame timing only.

The autopilot's play, for the record: Lobby — melee-killed guard G2
(Air Takedown), slipped past G3 into the elevator. Data Center —
Bullet-Time approach, melee-killed the Marksman at his post (Air
Takedown), stepped into the elevator zone; the Enforcer was outrun
(clear-OR-slip-past rule, same as the Lobby's). Penthouse — Bullet-
Time approach, melee-killed the Marksman, then an orbit-standoff gun
fight against the boss (player HP fell to 30 — the fight is real);
boss phase changes and burst fire were live throughout.

## Save-system verification

`save_system.py` landed at the project root during this build (after
recon, before the first full run). The specified interface matches
exactly — `SaveManager().save_stage_result(level_num, score,
time_taken, rank)`, `is_unlocked(level_num)`, plus
`get_level_record(level)`. No mismatch to flag. The bridge connected
live (`present=True`) and all six floor saves across runs 4–5 were
delivered. Read-back of the real save file
(`~/.actionstar/user_progress.json`) after the runs: all three levels
unlocked; level_1 best 8,662 / B (kept from run 2 — SaveManager only
replaces a record when the score improves; documented behaviour),
level_2 best 15,554 / S, level_3 best 24,786 / S.

## QA trail (honest failure history)

- **Run 1:** floor 2 FAILED — player killed in 12.25 s by the
  Marksman's lock-on fire at normal speed. Also: the harness exited 0
  despite the FAIL verdict (application.quit masks the code).
- **Run 2:** Bullet Time added to the floor-2 approach; still FAILED
  at 20.52 s. Exit code still masked.
- **Run 3 (instrumented):** forensics showed the player frozen at
  (11.2, −6.0) from t = 3.5 s — pushing head-on into partition_b's
  face, where the collision slide has no tangential component; the
  Marksman farmed the stationary target (4 × 30 dmg). Log evidence:
  `mrk_lock` climbing 0.34 → 1.39 under Bullet Time (the 0.3× world
  scaling working exactly as designed), Enforcer closing meanwhile.
- **Fixes:** floor-2 route bends north of the partition (tangential
  slide), a stuck detector in the autopilot's `nav()` inserts a
  perpendicular detour after 1.5 s without progress, and the harness
  enforces its exit code with `os._exit`. Runs 4 and 5 then passed
  27/27.

## Seams and uncertainties

1. **phase4 entry wiring:** `phase4/game_entry.launch_stage()` still
   shows its graded demo take. The pipeline emits its final record in
   exactly the `run_record` shape `VictoryScreen.show_result` consumes
   ({stage_id, stage_name, t_actual, t_target, combo_peak, completed,
   stunt_breakdown}) with `stage_id="full_run"`, and calls the real
   VictoryScreen when one is injected (proven in this test). Pointing
   the menu's stage start at `FullGamePipeline` is the entry point's
   own remaining step.
2. **Floor-2 goal zone:** `DataCenterLevel` defines no goal/elevator
   zone (verified in its source). The pipeline defines one —
   `DC_ELEVATOR_ZONE` (NE corner, x 16.5–19.5, z 10.0–12.5) — and
   renders a gold pad there so the goal is visible in the scene.
3. **Marksman damage:** the archetype ships no `take_shot_damage` /
   `take_melee_damage`. The pipeline adapter applies plain HP damage
   and the base class's own death path (`_die`); no behaviour was
   invented for him beyond being damageable.
4. **Shield Bypass in live play:** the adapter registration is
   unit-proven (flank kill → exactly one shield_bypass, 250 raw), but
   the passing runs did not exercise it live — the autopilot outran
   the Enforcer under the clear-or-slip-past rule rather than
   fighting him. The Enforcer kill path in a live floor is untested.
5. **Heal evidence:** floor 2's live heal was +0 (the Bullet-Time
   approach took no damage, HP stayed 100). The table itself is
   unit-proven for every rank and live-proven where it bit: floor 1's
   capped heal (93 +40 → 100, recorded +7) and floor 3's S settle
   (30 → 100 on paper; the run ends there, so it has no next-floor
   effect — the settle applies the rule uniformly).
6. **Design consequence of banking (flagged, not a bug):** because
   each floor's remaining is computed against its *effective* cap,
   banked time compounds — floor 3's cap reached ~258 s in these runs.
   That is the chain rule exactly as specified; if Cyrus wants banked
   time to decay or cap, it is a one-line change in
   `RunState.settle_floor` plus a re-run of this test.
7. **Audio/menus:** the pipeline does not drive phase4's SoundManager
   or menus; in standalone play the VictoryScreen's buttons Re-take
   (rebuilds the pipeline) and quit. Sound hookup belongs with the
   game_entry wiring in seam 1.
