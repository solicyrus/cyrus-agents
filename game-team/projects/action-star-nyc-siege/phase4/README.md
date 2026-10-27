# Phase 4 — Menus, Dynamic Audio, High Scores, Packaging

Finalization workstream A for **Action Star: NYC Siege 3D**
(Cyrus's Phase-4 order, 2026-10-27).

| File | What it is |
|---|---|
| `main_menu.py` | `MainMenuState` — cinematic 3D menu (tower backdrop, camera drift), START / STAGE SELECT (Lobby 90s · Data Center 75s · Penthouse 105s) / HIGH SCORES / SETTINGS / QUIT, callback state-machine interface |
| `game_ui_screens.py` | `SettingsMenu` (BGM/SFX/UI sliders, resolution + graphics selectors, key-guide panel), `VictoryScreen` (state-driven: ranked victory card **or** F Game Over, RE-TAKE / BACK TO MENU), `HighScoresScreen` |
| `sound_manager.py` | BGM/SFX/UI pipeline, per-channel volumes, `play_ui()`, Bullet-Time pitch via pre-rendered 0.4x variants |
| `scores_store.py` | Per-stage best takes → `high_scores.json` in the user-data folder |
| `game_settings.py` | Persisted settings + engine application (resolution, vsync/graphics) |
| `assets.py` | `asset_path()` (`sys._MEIPASS`-safe) + `user_data_path()` |
| `generate_audio_assets.py` | Synthesizes all v1 WAVs (numpy) + their bullet_time/ variants |
| `game_entry.py` | The packaged entry: menu shell state machine, stage-start handoff |
| `build_executable.py` + `main.spec` + `panda_runtime_hook.py` | PyInstaller packaging (see PACKAGING.md) |
| `test_audio_math.py` · `test_scores_store.py` · `test_menu_smoke.py` | QA — see TEST-REPORT.md |

All v1 audio is **synthesized** (no licensed assets exist yet) — see
`assets/manifest.json`. Controls shown in the key guide are the real
shipped mapping from `level1/main.py`: WASD move · mouse aim · LMB
shoot · RMB/F melee · C slide · L-SHIFT Bullet Time · R reload · ESC.
