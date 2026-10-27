# HUD QA Report — HUDManager headless smoke test

> گزارش تست HUD — اجرای واقعی در همین محیط (Xvfb + GL واقعی)، نه قول و ادعا. هر خط زیر خروجی ثبت‌شده‌ی اجراست.

## What was tested

`hud/test_hud_smoke.py` builds a minimal Ursina scene plus the real
`HUDManager` (layout per `../HUD-SPEC.md`) and drives a scripted ~5 s run
inside the engine's update loop:

- elapsed timer advances the whole run; target fixed at 120 s;
- three stunt notifications at t≈0.3 s: +200 WALL-RUN KILL, +150 AIR
  TAKEDOWN, +50 BULLET DODGE (Cyrus's approved matrix values);
- combo rises to 3.5x at t≈0.8 s — through `update_state()` AND an explicit
  `set_combo(3.5)` call; exactly one combo announcement must appear;
- HP drops 100 → 62 at t=1.5 s; Bullet Time charge drains 100 → 35 and
  refills to 100, ending in the READY state.

Assertions: no exception in any frame's `update_state()`, feed entries
spawn and expire on schedule (lifetime 2.6 s), the pool drains fully, and
the on-screen texts track the scripted state (read back from the live
Text entities — including the final "STUNT SCORE: 12,450" comma format
and "(Target: 02:00.00)").

The S_total formula itself is **not** re-tested here — it belongs to the
logic package's tests. This test only proves the HUD displays the totals
it is given and never interferes with the host loop.

## Run record

- Command: `xvfb-run -a /tmp/ursina-venv/bin/python hud/test_hud_smoke.py`
- Environment: `/tmp/ursina-venv` (Python 3.12.3, ursina 8.3.0, Panda3D
  1.10.16), Xvfb virtual display, real GL context (same setup as the
  Stage-1 feasibility prototype).
- **Exit code: 0 — PASS, 13 checks, 0 failures.**
- Frames: 242 frames in 5.21 s (≈46 fps under sandbox software rendering).

## Verbatim PROOF output

```
PROOF check feed_shows_wall_run_kill: OK feed=['+200 PTS  ⚡ WALL-RUN KILL', '+150 PTS  💥 AIR TAKEDOWN', '+50 PTS  ⚡ BULLET DODGE', '[ COMBO MULTIPLIER INCREASED TO 3.5x ]']
PROOF check feed_shows_combo_announcement: OK feed=['+200 PTS  ⚡ WALL-RUN KILL', '+150 PTS  💥 AIR TAKEDOWN', '+50 PTS  ⚡ BULLET DODGE', '[ COMBO MULTIPLIER INCREASED TO 3.5x ]']
PROOF check feed_entries_active_mid_run: OK active=4
PROOF check no_exception_in_update_state: OK frames=242 all update_state calls returned
PROOF check frames_sane: OK frames=242 in 5.21s
PROOF check notifications_spawned: OK spawned=4 (3 stunts + >=1 combo)
PROOF check feed_entries_expired: OK expired=4 (lifetime is 2.6s, run 5.2s)
PROOF check feed_pool_drained: OK active=0
PROOF check time_text_tracks_state: OK time_text='⏱️ TIME: 00:05.21 (Target: 02:00.00)'
PROOF check score_text_tracks_state: OK score_text='⭐ STUNT SCORE: 12,450'
PROOF check combo_text_tracks_state: OK combo_text='🔥 COMBO: 3.5x [WALL-RUN KILL + AIR TAKEDOWN]'
PROOF check hp_text_tracks_state: OK hp_label='HP: 62%'
PROOF check bullet_time_ready_state: OK status='⚡ READY (L-SHIFT)' label='BULLET TIME: 100%'
PROOF hud_smoke PASS: 13 checks, 0 failures, frames=242, spawned=4, expired=4
```

Notable behaviour confirmed by the run:

- **Exactly one** combo announcement spawned (total = 4) even though the
  3.5x rise arrived via both `update_state()` and an explicit
  `set_combo()` — the second call saw no increase and stayed silent.
- Feed pool: all 4 entries expired by end of run (active = 0); nothing
  leaks entities — the pool is created once in `HUDManager.__init__`.

## Honest limits

- The ≈46 fps figure is the sandbox's **software renderer** on a virtual
  display. It is NOT a GPU performance prediction; HUD cost on Cyrus's PC
  can only be judged on a real screen. What this run does prove: the HUD
  adds no per-frame entity creation and never raised in 242 frames.
- Emoji glyphs (⏱️ ⭐ 🔥 ⚡ 💥) are carried in the text strings (and read
  back verbatim above); how they rasterise depends on the fonts of the
  machine running the game — untested here.
- Audio, human control feel and camera behaviour remain untestable in
  this sandbox (same limits as the Stage-1 feasibility report).
