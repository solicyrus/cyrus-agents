# Save System + Level Select — Build & QA Report (2026-10-27)

Implements Cyrus's approved SaveManager design as the project's real
progress system, plus the Level Select screen. Files live at the
project root of `action-star-nyc-siege/`.

## Files

| File | Bytes | Role |
|---|---|---|
| `save_system.py` | 9,452 | SaveManager + `default_save_path()` |
| `level_select.py` | 5,612 | LevelSelectMenu (Ursina) |
| `test_save_system.py` | 8,291 | QA suite (logic + headless UI smoke) |
| `SAVE-SYSTEM-REPORT.md` | this file | report |

## Semantics — Cyrus's design, kept exactly

- Store: `user_progress.json` → `{unlocked_levels, levels_data}`.
- Fresh profile: only Level 1 unlocked; all records zeroed.
- `save_stage_result(level, score, time, rank)` replaces a floor's
  record ONLY when `score` beats `best_score`; the stored time and
  rank always describe that same best-scoring take.
- Any rank ≠ "F" unlocks floor N+1; the chain caps at Level 3.
- Titles: 1 "NYC Tower Lobby" · 2 "Data Center" · 3 "Penthouse & Helipad".

## Hardening over the raw pasted code (behavior unchanged)

- **Save path**: per-user writable directory via `default_save_path()`
  (Windows `%APPDATA%/ActionStar/`, else `~/.actionstar/`), with a
  constructor override for tests/portable mode. Never inside a
  PyInstaller bundle — `sys._MEIPASS` is read-only.
- **Crash-safe writes**: temp file in the same directory + `os.replace`
  (with fsync), so a mid-write crash can't corrupt the save.
- **Validation on load**: level numbers restricted to 1–3, per-field
  record checks, unknown keys tolerated, Level 1 always present;
  corrupt/missing file → fresh profile, no crash.
- Argument validation in `save_stage_result` (unknown level/rank or
  negative score/time raises `ValueError` instead of writing garbage).

## QA — run, not claimed

`python3 test_save_system.py` → **Part A: 15/15 PASS, exit 0**
(fresh profile, record store + unlock, F does not unlock, lower score
keeps record, reload persists identically, corrupt file → defaults,
no Level 4, default-path shape).

`xvfb-run -a /tmp/ursina-venv/bin/python test_save_system.py --require-ui`
→ **Part B: 8/8 PASS, exit 0** (Ursina 8.3.0, real GL context):

- card 1 text = `LEVEL 1 / NYC Tower Lobby / Best Score: 14500 / Best Rank: A / Best Time: 68.4s`
- card 2 unlocked, no 🔒; card 3 shows `🔒 LOCKED`
- `activate_card(3)` → `None`, callback list stays empty; the locked
  button's own `on_click` also fires nothing
- `activate_card(2)` → `2`, `on_level_chosen` received `[2]`;
  card 1's button handler appends `1`
- Back button fires `on_back`

Total: **23/23 checks PASS**. Sandbox note: no audio device here
(NullAudioManager fallback) — irrelevant to this system; rendering was
via Xvfb software GL as in earlier stages.

## Integration seams (for the pipeline / main-menu wiring)

```python
# save_system.py
SaveManager(save_path: str | None = None)          # None → default_save_path()
default_save_path() -> str
SaveManager.save_stage_result(level_num: int, score: int,
                              time_taken: float, rank: str) -> bool
SaveManager.is_unlocked(level_num: int) -> bool
SaveManager.get_level_record(level_num: int) -> dict   # copy
SaveManager.unlocked_levels -> list[int]              # property, copy
SaveManager.load_data() -> dict

# level_select.py
LevelSelectMenu(save_manager: SaveManager,
                on_level_chosen: Callable[[int], None] | None = None,
                on_back: Callable[[], None] | None = None)
LevelSelectMenu.activate_card(level_num: int) -> int | None
LevelSelectMenu.card_text(level_num: int) -> str
LevelSelectMenu.refresh() -> None      # call after any save_stage_result
LevelSelectMenu.destroy() -> None      # screen switch cleanup
LevelSelectMenu.cards -> dict[int, Button]
```

**Wiring recipe**: one shared `SaveManager()` is created at game
start; `full_game_pipeline.py` calls
`save_manager.save_stage_result(floor_num, s_total, t_actual, rank_letter)`
at the end of every floor; `main_menu.py`'s Stage Select opens
`LevelSelectMenu(save_manager, on_level_chosen=<start floor N>,
on_back=<return to menu>)`. The High Scores screen can read the same
records through `get_level_record`.

**Overlap note (decision for the manager, not merged here)**:
`phase4/scores_store.py` (Phase-4 worker) keeps richer per-stage
breakdowns in `records.json`. This save system is the progress/unlock
store Cyrus specified; the two stores should be reconciled at wiring
time (one shared instance passed to both) rather than either being
deleted blindly.
