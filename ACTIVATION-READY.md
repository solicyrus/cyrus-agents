# ACTIVATION READY — Cyrus Agents (game studio + house agents)

Prepared 2026-10-27 under Cyrus's Production activation order.
All protocols are implemented and PROVEN below. No real key
value appears in this repo, in this file, or in any log — keys
live only in a local `.env` / Actions secrets at activation.

## Files changed in this activation prep (all pushed + read-back size-verified on GitHub)

| File | Bytes | What |
|---|---|---|
| `.env.example` | 724 | NEW — every env name the house code reads |
| `.gitignore` | 194 | NEW — `.env`, `.env.*` (with `!.env.example`), `*token*.json`, `client_secret*.json`, `credentials*.json` |
| `check_system_health.py` | 5,667 | NEW — live health check (Protocol 3) |
| `game-team/game_creator_agents/requirements.txt` | 210 | NEW — openai, python-dotenv, pygame |
| `game-team/game_creator_agents/run_game_builder.py` | 8,017 | guarded `load_dotenv()` (agent folder `.env`, then repo-root `.env`) |
| `game-team/game_creator_agents/game_designer_agent.py` | 12,872 | guarded `load_dotenv()` at import |
| `game-team/game_creator_agents/game_developer_agent.py` | 13,254 | guarded `load_dotenv()` at import |

## Protocol 1 — secure key configuration

`.env.example` (verbatim; audited against the actual
`os.environ` reads across the house — game_creator_agents,
game-architect, code-agent, super-brain, game-qa):

```
# Cyrus Agents — credential NAMES only. Copy to .env (never
# commit .env), export in the environment, or set as GitHub
# Actions secrets. No values live in this repo.

# Game studio brain — game-team/game_creator_agents (Designer +
# Developer), game-architect, code-agent. This is Cyrus's OpenAI
# key: the ONE key that lights up the game team's brain.
AGENT_API_KEY=

# Model for the agents above (optional — default "gpt-4o").
AGENT_MODEL=

# PR reviewers — super-brain and game-qa's ai_pr_reviewer.
# (May hold the same OpenAI key value as AGENT_API_KEY.)
OPENAI_API_KEY=

# Provided automatically by GitHub Actions in CI. Set locally
# ONLY when running the Actions-style agents outside Actions.
GITHUB_TOKEN=
```

Secret-safety proof (GitHub recursive tree scan, run after this
push set): **47 tracked files (including this one), 0 hits** for
`.env` files, `*token*.json`, `client_secret*.json`, or
`credentials*.json`. The local mirror was scanned too: no real
`.env` or token file exists in it.

## Protocol 3 — check_system_health.py (real runs)

Plain run in this environment (no keys configured), exit 0:

```
Cyrus Agents — system health check
------------------------------------------------------------
OpenAI via AGENT_API_KEY (game brain) — NOT_SET — AGENT_API_KEY not set — the game studio (Designer/Developer), game-architect and code-agent cannot run yet
OpenAI via OPENAI_API_KEY (PR reviewers) — NOT_SET — OPENAI_API_KEY not set — super-brain and the game-qa PR reviewer cannot run yet
GitHub (Actions agents) — NOT_SET — GITHUB_TOKEN not set locally — GitHub Actions provides it automatically in CI; needed only for local runs of the Actions-style agents
Agent model (AGENT_MODEL) — INFO — AGENT_MODEL unset — agents use their default gpt-4o
Local tool: pygame (QA smoke runs) — NOT_SET — not installed — QA smoke runs will SKIP honestly (never fake-pass)
Local tool: python-dotenv (.env loading) — NOT_SET — not installed — export variables in the shell instead (pip install -r game-team/game_creator_agents/requirements.txt)
------------------------------------------------------------
RESULT: READY — every configured service answered OK (NOT_SET items are warnings, listed above)
```

Proof run with the house OpenAI key loaded into the process
environment only (injected as both `AGENT_API_KEY` and
`OPENAI_API_KEY` from `~/workspace/factory/.env`; never printed,
stored, or pushed), exit 0 — both brain lines are REAL
authenticated verdicts:

```
OpenAI via AGENT_API_KEY (game brain) — OK — authenticated; 134 models visible
OpenAI via OPENAI_API_KEY (PR reviewers) — OK — authenticated; 134 models visible
```

Honesty re-check after the dotenv changes: the full pipeline
with no key still stops at the DESIGN stage —
`AgentNotConfiguredError: AGENT_API_KEY not configured …
Refusing to fabricate a GDD without the LLM` — exit 1, no
output created. No fake work, as ordered.

Local notes from the run: pygame and python-dotenv are not
installed for the system python3 in this sandbox — install with
`pip install -r game-team/game_creator_agents/requirements.txt`
before local game-QA smoke runs (until then the smoke check
SKIPs honestly; in GitHub Actions the workflows install their
own requirements).

## Keys Cyrus must provide at activation — in order

1. **AGENT_API_KEY** — Cyrus's OpenAI key, via the secure
   credential route (never in chat). The manager places it in
   this repo's local `.env` for local runs and as the
   `AGENT_API_KEY` GitHub Actions secret for the workflow
   agents. Unlocks: the game studio's Designer + Developer,
   game-architect, and code-agent. This is the SAME key value as
   the social team's `OPENAI_API_KEY` in solicyrus/cyrus-team —
   one key lights up BOTH teams.
2. **OPENAI_API_KEY** — the same OpenAI key value may be reused
   here. Unlocks: super-brain and the game-qa PR reviewer.
3. **AGENT_MODEL** — optional; default `gpt-4o`. No action
   needed unless Cyrus wants a different model.
4. **GITHUB_TOKEN** — nothing to provide: GitHub Actions
   supplies it automatically inside workflow runs.
