# Game Tester run — 2026-10-27 16:25:37 UTC

Project: `/tmp/game-proof-fail`
Overall: **FAILURES PRESENT (1 failed, 2 ran, 2 skipped)**

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | pytest | FAIL | pytest exit 1 — ... =================================== FAILURES =================================== ___________________________________ test_bad ___________________________________ def test_bad(): > assert 1 + 1 == 3 E assert (1 + 1) == 3 test_bad.py:2: AssertionError =========================== short test summary info ============================ FAILED test_bad.py::test_bad - assert (1 + 1) == 3 1 failed in 0.01s |
| 2 | npm test | SKIP | no package.json |
| 3 | Python syntax compile | PASS | all 1 .py file(s) compile cleanly |
| 4 | Godot headless check | SKIP | godot is not on PATH |

Read-only run: checks were executed, nothing in the project was changed.
The Game Tester never fixes anything; failures go to the manager.
