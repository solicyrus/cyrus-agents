# Cyrus Game Team 🎮 — تیم ایجنت‌های بازی سایرس

This is the **game wing** of the Cyrus agent house (`solicyrus/cyrus-agents`).
It was built on 2026-10-27 at the owner's order: first the agent team is set
up and proven, then game work begins.

## How the team works (the manager model)

- **Owner — Cyrus.** He gives the ideas, the program, and the approvals.
- **Manager — Cyrus (the assistant).** He assigns the work, checks every
  result, and brings only verified results back to the owner.
- **Agents — the workers below.** Each one has one job, written in its
  `AGENT.md`. An agent's AGENT.md is its constitution: if a report and the
  AGENT.md disagree, the AGENT.md wins.

## The roster

| Agent | Folder | Job (one line) |
|---|---|---|
| 🎮 Game Builder | `game-builder/` | Writes and fixes the game's code, step by step, and proves each change with tests. |
| 🔎 Game Reviewer | `game-reviewer/` | Reads every game code change (Pull Request) and reports bugs, risks, and quality problems. |
| 🧪 Game Tester | `game-tester/` | Runs the game's checks (tests, syntax, engine check) and reports PASS / FAIL honestly — it never fixes. |

The Game Builder and Game Reviewer are game-tuned copies of the house
Code Agent and Super Brain — same proven engines, game دستور. The Game
Tester is a new deterministic agent (no AI brain, like the Tour Guardian):
plain code, plain evidence, zero cost per run.

## The quality gate (house rule)

- **No agent works unproven.** Every agent first passes a small real
  **trial task** that the manager inspects.
- **The manager reviews everything.** Agent work lands as Pull Requests /
  reports — never directly on the live game.
- **Nothing goes live directly.** No publishing, no payments, nothing
  irreversible without the owner's approval, relayed through the manager.
- **Honest, with evidence.** An honest FAIL always beats a false PASS.

## Status

**Installed, dormant.** The Builder and Reviewer wake only when the OpenAI
key is added as a GitHub repository secret (the same arrangement as the
house agents: `AGENT_API_KEY` for the Builder, `OPENAI_API_KEY` for the
Reviewer). The Tester needs no key and can be run by the manager at any
time. No game has been chosen yet — team first, game choice after.
