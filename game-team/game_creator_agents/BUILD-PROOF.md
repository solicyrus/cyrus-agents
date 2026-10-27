# Game Creator Agents — Build Proof

Built 2026-10-27 under Cyrus's executive order for the Game Studio pipeline
(`game_creator_agents/` — the runnable code of the studio; the charter agents
game-director / game-architect / game-qa live beside it unchanged).

## Files

| File | Role |
|---|---|
| `game_designer_agent.py` | The Visionary Director as code: `analyze_idea()` → LLM (strict JSON) → `GDD` dataclass → deterministic `validate_gdd()`; incomplete output raises, listing the gaps. |
| `game_developer_agent.py` | The Lead Architect as code: `generate_game()` — one LLM call per module (config/entities/main), each module rejected before disk-write if it trips `find_placeholders()` or fails to compile. |
| `game_qa_agent.py` | The QA Destroyer as code: fully deterministic, stdlib only — compile check, placeholder scan, headless pygame smoke run, perf sanity. FAIL = fix order with reasons. |
| `run_game_builder.py` | The pipeline: idea → designer → developer → QA; `--qa-only <dir>` runs QA alone. Any stage failure stops the chain loudly, exit 1. |

Environment for proofs: Python 3.12.3; pygame 2.6.1 in a scratch venv
(`/tmp/qa-venv`) for the smoke runs; fixtures kept outside the repo in /tmp.

## Proof 1 — all four files compile

```
$ python3 -m py_compile game_designer_agent.py game_developer_agent.py game_qa_agent.py run_game_builder.py
PY_COMPILE: all 4 OK
```

## Proof 2 — fixture A: a real pygame game → QA PASS, smoke run exercised

Fixture A (`/tmp/fixture_good_game/main.py`): a genuine pygame game — window
loop, a bouncing sprite, a live score counter drawn on screen, auto-quit
after 240 frames so headless runs terminate cleanly.

```
$ /tmp/qa-venv/bin/python game_qa_agent.py /tmp/fixture_good_game
QA Report — /tmp/fixture_good_game
Overall: PASS
Checks:
  [PASS] compile: all 1 Python files compile
  [PASS] placeholders: no placeholder/stub patterns in 1 files
  [PASS] smoke_run: main.py exited cleanly (code 0) after 3.99s headless
  [PASS] perf_sanity: 1 Python files, 2504 bytes, 77 lines, smoke wall time 3.99s
exit=0
```

## Proof 3 — fixture B: broken project → QA FAIL, both defects named

Fixture B (`/tmp/fixture_bad_game/`): `main.py` has a syntax error
(`def start_game()` missing its colon); `enemies.py` contains
`# TODO: Implement logic for enemy movement and attacks` over a bare `pass`.

```
$ /tmp/qa-venv/bin/python game_qa_agent.py /tmp/fixture_bad_game
Overall: FAIL
  [FAIL] compile: 1 of 2 files failed to compile: main.py: ... SyntaxError: expected ':'
  [FAIL] placeholders: 2 placeholder/stub findings: enemies.py: line 6: TODO marker:
         '# TODO: Implement logic for enemy movement and attacks';
         enemies.py: line 7: bare 'pass' stub line: 'pass'
  [FAIL] smoke_run: main.py exited with code 1 after 0.02s: SyntaxError: expected ':'
  [PASS] perf_sanity: 2 Python files, 364 bytes, 15 lines, smoke wall time 0.02s
Rejected items (fix order): compile + both placeholder findings + smoke_run, each with reasons.
exit=1
```

## Proof 4 — the pipeline entry point (`--qa-only`)

```
$ /tmp/qa-venv/bin/python run_game_builder.py --qa-only /tmp/fixture_good_game
[...] STAGE QA: start — project: /tmp/fixture_good_game
Overall: PASS ... PIPELINE RESULT: QA PASSED        exit=0

$ /tmp/qa-venv/bin/python run_game_builder.py --qa-only /tmp/fixture_bad_game
Overall: FAIL (same named defects as Proof 3)
PIPELINE RESULT: REJECTED BY QA — see the fix order above   exit=1
```

## Proof 5 — SKIP is honest, never a fake PASS

With the system Python (no pygame installed), the smoke check reports SKIP
with its reason and does not pretend to have run:

```
  [SKIP] smoke_run: pygame is not installed in this environment, so the headless
         smoke run cannot be exercised (install pygame to enable it)
```

## Proof 6 — no key, no fake output (LLM stages refuse loudly)

```
$ env -u AGENT_API_KEY python3 run_game_builder.py "a tiny game about a cat collecting stars" --out /tmp/should_not_exist_game
[...] STAGE DESIGN: start — analysing the raw idea into a GDD
[...] STAGE FAILED: DESIGN stage failed: AgentNotConfiguredError: AGENT_API_KEY not
      configured: set the AGENT_API_KEY environment variable (or GitHub secret)
      before running the designer agent. Refusing to fabricate a GDD without the LLM.
PIPELINE RESULT: STOPPED at the DESIGN stage        exit=1
(no output directory was created)
```

## «نمی‌شه yet» — honest not-yet list

- **The LLM stages (`analyze_idea`, `generate_game`) are code-complete but NOT
  live-proven.** This environment has no AGENT_API_KEY, so no real OpenAI call
  has been made through them; their refusal path is proven (Proof 6) and their
  internal guards (JSON parsing, GDD validation, placeholder/syntax rejection)
  are deterministic code — but the generation quality itself can only be
  proven after activation, i.e. when AGENT_API_KEY is provided as a GitHub
  secret / environment value and AGENT_MODEL is set (default gpt-4o).
- **Non-Pygame engines are not generated yet.** `generate_game` detects an
  engine named by the GDD and, for anything other than Pygame, raises a loud
  "not configured for that engine" error instead of pretending (Godot/JS
  support is future work for the Architect).
- **The QA smoke run needs pygame in the QA environment.** Where pygame is
  absent it reports SKIP with the reason (Proof 5); it was fully exercised
  here via the scratch venv (Proofs 2–4).

---

## Addendum 2026-10-27 (evening) — cross-module consistency gate + rebuild

**Background (first real run, after activation):** the LLM stages went live
with AGENT_API_KEY set and ran end to end — but QA REJECTED the generated
"Apple Catcher": `main.py` imported `SCREEN_WIDTH` from `config.py`, which
never defined it (smoke-run ImportError). Per-module generation had no
cross-module consistency. The game was not hand-fixed; Cyrus approved fixing
the developer instead («و اصلاح»).

**The fix (in `game_developer_agent.py`):**
1. **Context:** each module after the first is now generated with the FULL
   source of every already-generated module in its prompt, with an explicit
   instruction (user + system prompt) to import ONLY names that actually
   exist in those sources, and to define anything missing locally instead.
2. **Consistency gate (deterministic, AST):** `find_consistency_errors()` /
   `validate_project_consistency()` run over the whole in-memory project
   before anything reaches disk. Every `from sibling import X` and every
   `sibling.Y` attribute use (aliases honoured) must resolve to a name the
   target module actually defines (assignments, defs, classes, top-level
   imports). Any miss raises `CodeRejectedError` listing each unresolved
   name — no partial output is written, and names are never silently
   patched by the developer itself.

### Proof 7 — the gate, on synthetic pairs (original broken pair reconstructed from the failure record; the first run's /tmp output no longer exists)

```
CASE 1 (config.py without SCREEN_WIDTH + main.py importing it)
  errors: ["main.py: imports 'SCREEN_WIDTH' from config.py, but config.py
            never defines 'SCREEN_WIDTH'"]
  -> validate_project_consistency raised CodeRejectedError naming SCREEN_WIDTH
CASE 2 (consistent 3-module project: config + entities + main)
  errors: []  -> gate passed
CASE 3 (main.py uses entities.MissCounter, which entities.py never defines)
  errors: ["main.py: uses 'entities.MissCounter', but entities.py never
            defines 'MissCounter'"]  -> caught
GATE PROOF: ALL CASES OK
```

### Proof 8 — rebuild with the same idea, one run only

```
$ run_game_builder.py "Catch falling apples in a basket with arrow keys;
  score for each catch; game over after 3 misses" --out /tmp/apple-catcher-rebuild
STAGE DESIGN: ok — GDD validated complete: 'Apple Catch Frenzy' (Arcade)
STAGE BUILD:  config.py (645 B), entities.py (2,974 B), main.py (1,119 B)
  log: "Cross-module consistency gate passed for 3 modules" (before disk-write)
STAGE QA: verdict: PASS (0 rejections)
  [PASS] compile: all 3 Python files compile
  [PASS] placeholders: no placeholder/stub patterns in 3 files
  [PASS] smoke_run: main.py exited cleanly (code 0) after 4.95s headless
  [PASS] perf_sanity: 3 Python files, 4,738 bytes, 173 lines
PIPELINE RESULT: GAME BUILT AND QA PASSED        exit=0
```

This also retires the first «نمی‌شه yet» bullet above: the LLM stages are
now live-proven end to end (design → build → QA), first with a QA rejection
that exposed a real defect, then — after the developer fix — with a QA PASS
on the identical idea.
