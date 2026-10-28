# Color Fix Report — the white-screen bug (2026-10-27)

## Symptom

On the boss's Windows laptop the game booted cleanly (no errors in the
log, menu built, BGM playing) but rendered an almost entirely **white
screen**: no menu title, no buttons, only two dark vertical bars and the
faint development-mode counters. The same frame was then reproduced in
the sandbox — proving it was never a Windows/GPU problem. The game had
rendered this way everywhere; nobody had ever looked at a rendered
pixel before the human test.

## Root cause

**Ursina 8.3 changed the semantics of `color.rgb()`.**

In Ursina 8.3, `color.rgb()` is an alias of `color.rgba()` and takes
**0..1 floats**. The 0..255 constructor is a different function:
`color.rgb32()` / `color.rgba32()`.

The codebase was written against the old convention and passed 0..255
values into `color.rgb()` everywhere — e.g. `color.rgb(52, 55, 64)` for
the menu's dark ground slab. Under 8.3 semantics those values clamp to
1.0, so nearly every entity became **(1, 1, 1, 1) — pure white**. Only
near-black colors survived as visible shapes (the two "bars" on the
boss's screen were the darkest towers).

Proof before the fix: `entity.get_color()` on a backdrop entity
returned `(1, 1, 1, 1)` despite the code specifying dark navy values.

## The fix

Mechanical conversion of every affected call site to the 0..255
constructor:

- `color.rgb(r, g, b)` → `color.rgb32(r, g, b)`
- `color.rgba(r, g, b, a)` (0..255 form) → `color.rgba32(r, g, b, a)`

No logic changed; no values changed; only the constructor now matches
the numbers the code always intended.

## Scope

- **110 call sites** converted across **17 files**:
  `prototype3d.py`, `hud/hud_manager.py`, `hud/test_hud_smoke.py`,
  `level1/lobby_level.py`, `level1/player_controller_3d.py`,
  `level1/enemy_ai_3d.py`, `stage3/destructibles.py`,
  `stage3/data_center_level.py`, `stage3/penthouse_level.py`,
  `stage3/enemy_archetypes.py`, `stage3/boss_hud.py`,
  `phase4/game_ui_screens.py`, `phase4/main_menu.py`,
  `level_select.py`, `full_game_pipeline.py`, `character_model.py`,
  `intro_card.py`
- Audit found **no 4-argument `color.rgb()` calls** and **no direct
  `Color()` misuse** anywhere in the project.

## Verification

- **Rendered frames, inspected by eye** (the check that was missing):
  headless screenshots of the main menu (navy/gold cinematic backdrop,
  legible title and buttons) and of Lobby gameplay (readable room,
  character, HUD) now show the intended colors.
- Full regression re-run after the fix, all green:
  logic **104/104**, pipeline **30/30**, full cycle **27/27**,
  character **40/40**, menu **23/23**, HUD **13/13**, audio PASS,
  save PASS.

## Known cosmetic wart (not part of this fix)

Some HUD icon glyphs (⚡ / 🏆) render as hollow boxes in the bundled
font — the glyphs are missing from the font, not a color problem.
Tracked as a cosmetic issue only; text and numbers are unaffected.

## Lesson (locked)

The entire QA history of this project was **state-based**: tests
asserted entity positions, enabled flags, scores and readbacks — and
never rendered a single pixel. Every suite was green while the game
was visually broken on every machine.

**Rule going forward: no visual feature is "verified" without a
rendered-frame screenshot inspected by eye.** The human test caught in
one minute what 300+ automated checks could not.
