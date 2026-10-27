# Stage 3 — TEST REPORT (Floor 2 Data Center + Floor 3 Penthouse/Boss)

**Date:** 2026-10-27 · **Engine:** Ursina 8.3.0, headless under Xvfb (real GL
context, sandbox software rendering) · **Test:** `stage3/test_stage3_smoke.py`
**Verdict: PASS — 30/30 checks, exit 0.**

## What was built

| File | Contents |
|---|---|
| `stage3/data_center_level.py` | `DataCenterLevel` (target **75 s**): rack rows, smoked-glass meeting room, monitoring wall, corridor partitions; `ServerRack` hazards — a shot-out rack discharges and **stuns enemies within 4.5 u for 3.0 s**; sprinkler system (6 shots / 5 s in one quadrant → 12 s of rain, camera water film, `visibility_factor` 0.55) |
| `stage3/penthouse_level.py` | `PenthouseLevel` (target **105 s**, boss included): panoramic **breakable** `WindowPane`s (10), infinity pool, spiral staircase (14 steps) to the roof helipad, roof **wind** (`wind_at` / `move_speed_factor_at`: ×0.62 against, ×1.38 with), `throw_enemy_out()` registering **defenestration** |
| `stage3/enemy_archetypes.py` | `EnforcerEnemy` (850 HP, riot shield — frontal shots/melee **blocked**, slide-under + flank land; shotgun advance), `MarksmanEnemy` (red laser entity, 1.5 s lock-on, 30-dmg shot), `BossEnemy` "Syndicate Boss — Commander Vane" (1200 HP, **3 phases** at 66%/33%, burst fire 3/5/7, smoke grenades that block sight, cover repositioning, `hud_data()`) |
| `stage3/boss_hud.py` | `BossHealthBar` — dedicated HUD boss bar (Cyrus addendum): hidden until `begin_fight()`, fill + HP text + phase label re-rendered from `hud_data()` every `update()`, hides when the boss dies |
| `stage3/destructibles.py` | `DestructibleCover` — wooden desks / plaster columns take bullet damage and **break**: the solid is removed from the shared CollisionWorld and the box collapses to rubble |
| `logic/stunt_manager.py` (edit) | Stunt Matrix += `defenestration` **500**, `shield_bypass` **250** (both also in `KILL_ACTIONS`); logic suite re-run: **104/104 PASS** (see logic/TEST-REPORT.md addendum) |

## Acceptance checks — verbatim PROOF output of the passing run

```
PROOF check levels_built: OK dc_solids=26 ph_solids=29 panes=10 targets: dc 75s ph 105s
PROOF check a_glass_ray_blocked: OK hit=(9.825, 'smoked_glass_partition_1')
PROOF check a_glass_stops_before_guard: OK glass at 9.82u; the guard behind the glass stands at 14.00u — the round never reaches him
PROOF check b_rack_discharged: OK result={'hp': 0.0, 'shock_triggered': True, 'stunned': ['ENF-DC']}
PROOF check b_enemy_stunned: OK stunned=['ENF-DC']
PROOF check b_stunned_enemy_does_not_act: OK moved=0.000u while stunned
PROOF check b_stun_expires: OK after 3.5s of ticks stun_until passed
PROOF check h_sprinklers_active: OK active=True zone=(0, 0)
PROOF check h_visibility_reduced: OK visibility=0.55
PROOF check i_desk_breaks: OK broke=True hp=0.0
PROOF check i_ray_passes_after_break: OK before=(3.25, 'desk_wood_west') after=(23.0, 'wall_north')
PROOF check c_frontal_shot_blocked: OK result=blocked hp=850 blocked=1
PROOF check c_flank_shot_damages: OK result=hit hp=800
PROOF check c_slide_under_damages: OK result=hit hp=750 (slide-under bypasses the shield)
PROOF check d_laser_entity_exists: OK laser entity constructed with the marksman
PROOF check d_laser_paints_target: OK laser_active seen during lock-on: True
PROOF check d_lock_on_fired_and_hit: OK shots=1 hit=True player_hits=1
PROOF check e_pane_broken: OK result={'pane': 'window_south_3', 'stunt_points': 750}
PROOF check e_defenestration_registered: OK event=StuntEvent(action_type='defenestration', base_points=500, multiplier_applied=1.5, points_awarded=750, timestamp=0.0, is_kill=True) (500 base x1.5 first-action combo = 750)
PROOF check e_combo_math_intact: OK raw_base=500 rated_total=750
PROOF check e_enemy_defeated_outside: OK alive=False state=defenestrated pos=Vec3(3.83, 0.45, -20.5)
PROOF check f_bar_hidden_before_fight: OK no boss fight yet -> the bar is not on screen
PROOF check f_boss_spawned_data_readable: OK hud_data={'name': 'SYNDICATE BOSS — COMMANDER VANE', 'hp': 1200.0, 'max_hp': 1200.0, 'fraction': 1.0, 'phase': 1, 'alive': True}
PROOF check f_bar_shows_full_hp: OK fraction=1.0 fill=0.600 text='1200 / 1200 HP'
PROOF check f_bar_tracks_hp_after_damage: OK fraction=0.583 (boss 0.583) fill=0.350 text='700 / 1200 HP' name='SYNDICATE BOSS — COMMANDER VANE — PHASE 2'
PROOF check f_phase_transition_at_66pct: OK phase=2 events=[('phase_change', 0.0, 2)]
PROOF check f_smoke_grenade_blocks_sight: OK grenades=1 sight_blocked=True
PROOF check f_bar_hides_when_boss_dies: OK boss alive=False bar visible=False
PROOF gate_g frames=76 elapsed=4.05s fps=18.8 (sandbox software rendering)
PROOF check g_fps_measured_with_boss_and_3_enemies: OK fps=18.8 boss_shots=6 enforcer_shots=10 marksman_shots=2 guard_shots=3
PROOF check g_boss_bar_live_during_fight: OK fraction=1.00
PROOF stage3_smoke PASS: 30 checks, 0 failures: []
```

## Notes & honest limits

- **FPS (check g):** 18.8 FPS in the recorded run (76 frames / 4.05 s) and
  21.3 FPS in an earlier identical run — boss + Enforcer + Marksman + Guard
  all live, real projectiles flying. This is the sandbox's **software
  renderer** on a virtual display: a floor for playability evidence, NOT a
  prediction of GPU frame rates on a real machine.
- **Boss bar (addendum):** asserted by reading back the widget's rendered
  state — `displayed_fraction` 1.000 → 0.583 after exactly 500 damage,
  `fill scale_x` 0.600 → 0.350 (= 0.60 × fraction), HP text "700 / 1200 HP",
  name label switching to "PHASE 2", bar hidden before the fight and after
  the boss's death.
- **Stun scope:** rack discharges stun enemies exposing `apply_stun()`
  (all Stage-3 archetypes). The Stage-1 `Guard` class predates that API;
  the level only calls it where it exists (`hasattr` guard) — no level1
  file was modified.
- **Vertical traversal:** the penthouse staircase is built geometry; the
  project's collision model is planar per floor plate (same honest scope
  as Stage 2). Wind is real level state (drift vector + speed factor +
  visibly drifting dust), consumed by movement code via the level API.
- The Marksman's hit rule: he only fires with a live sight line at the
  trigger moment (the lock breaks when cover intervenes), so a target
  that breaks LOS during the 1.5 s lock is genuinely missed.
