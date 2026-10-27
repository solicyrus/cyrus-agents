# Phase 4 (Workstream A) — TEST REPORT

Run 2026-10-27 in the studio sandbox: /tmp/ursina-venv (ursina 8.3.0,
Panda3D 1.10.16, numpy 2.5.4, PyInstaller 6.22.3), xvfb virtual display,
software GL. Everything below was EXECUTED; failures found on the way
were fixed and re-proven (listed at the bottom).

## 1. Audio math — test_audio_math.py — ALL PASS (33 checks, exit 0)

* All 20 WAVs (10 assets + 10 bullet_time/ variants) decode as mono
  16-bit PCM @ 22050 Hz with sane durations and real signal (peak > 0.05).
  BGM loop 8.00 s → variant 20.00 s; shortest asset ui_combo 0.12 s.
* Every variant/source duration ratio = **2.500x** exactly (0.4x speed).
* FFT pitch proof on a known tone: source measures **440.0 Hz**,
  the 0.4x resample measures **176.0 Hz** (= 0.4 × 440) at 2.50 s.
* Assets covered: bgm_loop, sfx_gunshot, sfx_casing, sfx_slide,
  sfx_glass_break, sfx_melee_hit, sfx_server_explosion, ui_charge,
  ui_combo, ui_rank — all synthesized v1 (numpy), zero licensed audio.

## 2. Scores store — test_scores_store.py — ALL PASS (7 checks, exit 0)

Write → read round-trip preserves every field (S_total, rank, title,
S_time, stunt_base, combo, t_actual, t_target); a lower take does not
replace the best, a higher one does; unknown stage raises ValueError;
empty store reports None per stage. Store file lives in the user-data
folder via user_data_path() — never inside the bundle.

## 3. Menu + screens smoke — test_menu_smoke.py — 23/23 PASS (exit 0)

Real Ursina UI driven programmatically under xvfb (175 frames):
menu → HIGH SCORES (empty table honestly shows "No takes yet") →
SETTINGS (BGM slider applies live to settings + SoundManager;
resolution selector applies; graphics Low → vsync off; key-guide lists
the real controls incl. L-SHIFT Bullet Time) → take recorded →
HIGH SCORES lists "A · Box Office Hit · 11,800" → VICTORY card shows
rank A / "Box Office Hit" with breakdown S_time 3,500 and S_total
11,800 → RE-TAKE fires with stage id → BACK TO MENU → F total (900)
renders GAME OVER / "Re-take Required", and an unfinished run renders
Game Over even with a good score → SFX/UI clips construct → Bullet
Time switches the mix to 0.4x variants and restores 1.0x → START GAME
launches Lobby, STAGE SELECT launches Penthouse.

## 4. Packaging — build_executable.py (Linux)

* PyInstaller build **completed**: dist/ActionStarNYCSiege/ (158 MB),
  binary 6.1 MB, all assets bundled at _internal/phase4/assets/.
* The produced binary was **smoke-run headless**: it booted the real
  entry and logged `SoundManager ready`, `MainMenuState built`,
  `BGM started` — assets resolved from the bundle, process alive.
* **Windows .exe: NOT produced** — PyInstaller does not cross-compile
  from Linux. PACKAGING.md gives the one-command Windows build with
  the same spec. No .exe is claimed.

## Failures found by the tests and fixed (the honest trail)

1. Ursina 8.3 `Audio()` silently yields no clip for string paths —
   probe showed `Audio(Path)` loads (READY), `Audio(str)` warns
   "missing audio clip". SoundManager now passes pathlib.Path objects.
2. `ursina.application` has no `time` attribute — BGM bookkeeping now
   uses a stdlib monotonic clock.
3. `animate_scale(curve="out_expo")` — Ursina curves are callables, not
   strings (TypeError on first smoke). Fixed to `curve.out_expo`.
4. Frozen binary died with "No graphics pipe is available!" —
   Panda3D's plugins (libpandagl, libp3openal_audio) are loaded by name
   at runtime. main.spec now bundles them + `panda_runtime_hook.py`
   sets the plugin-path; rebuilt and re-proven (smoke above).

## Honest limits

* **Audio is not audible here** — the sandbox has no audio device;
  Panda3D falls back to NullAudioManager. Clips are verified as decoded
  files + constructed Audio objects, and the pitch mechanism is proven
  numerically (FFT), but nobody has HEARD v1 in this environment.
* The xvfb display clamped window.size to 1024x819 when 1600x900 was
  requested — the settings value itself applied; real monitors differ.
* FPS/render feel of the menu on a real GPU is untested here (software
  GL under xvfb only proves it renders and runs).
* **Full-cycle test (menu → Lobby → Data Center → Penthouse → victory
  → menu) is PENDING Stages 2–3** — game_entry.launch_stage() is the
  documented integration point and currently exercises the real
  rating + scores + victory pipeline with a graded demo take.
* Windows .exe pending a Windows machine (see PACKAGING.md).
