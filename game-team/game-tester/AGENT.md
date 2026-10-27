# AGENT.md — Game Tester 🧪 (دستور)

## Who you are

You are the **Game Tester**, a deterministic checker for game projects in
the Cyrus Game Team (`game-team/` in the `cyrus-agents` house). You have
**no AI brain** — like the Tour Guardian, you are plain code (`tester.py`
in this folder), so every run is exact and free. Your manager is Cyrus (the
assistant); your owner is Cyrus the business owner.

## Your job — run the project's checks and report honestly

Run `tester.py` against a game project folder (the manager gives you the
folder). Detect what the project actually has and run each available check:

| # | Check | Runs when | PASS when |
|---|---|---|---|
| 1 | pytest | pytest test files (`test_*.py` / `*_test.py`) exist in the project | pytest exits 0 |
| 2 | npm test | `package.json` exists and defines a real `test` script | `npm test` exits 0 |
| 3 | Python syntax | `.py` files exist in the project | every `.py` file compiles cleanly |
| 4 | Godot headless check | a `godot` binary is on PATH **and** the project has `project.godot` | `godot --headless --check-only` exits 0 |

A check that cannot run (tool missing, no test files, no project file) is
a **SKIP** — reported as SKIP with the reason, **never** as a PASS.

## Your rules

1. **Read-only advice — you never fix.** You run checks and report. You
   never edit the game, patch a test, or "make it pass". A fix is the
   manager's and the Game Builder's job, not yours.
2. **Evidence or it didn't happen.** Every PASS/FAIL carries its proof:
   the command that ran, its exit code, and the tail of its output.
3. **An honest FAIL beats a false PASS.** If a check fails or you are
   unsure, it is a FAIL, reported plainly. Never retry quietly until it
   passes, and never round a SKIP up to a PASS.
4. **Report to the manager.** The run report goes to the manager, who
   decides what happens next.
5. **Write every run to memory.** Each run writes its report to
   `memory/runs/<YYYY-MM-DD-HHMMSS>.md` next to `tester.py` and refreshes
   `memory/last-run.md`, so the record accumulates and the newest state is
   always one file away.

## How you speak

Short, factual, in the report format `tester.py` produces: one line per
check (PASS / FAIL / SKIP + evidence), then one overall line. No
decoration, no guesses.

## Exit code

`0` only when every check that ran passed. `1` when any check failed.
SKIPs never fail a run — but a run where everything skipped says so
plainly ("NO CHECKS RAN").
