# Cyrus Game Studio 🎮 — استودیوی بازی‌سازی سایرس

This is the **game studio** inside the Cyrus agent house
(`solicyrus/cyrus-agents`). It was restructured on 2026-10-27 to match the
boss's **Game Studio Charter**: an independent, super-smart game studio
whose one job is turning the raw idea in the boss's head into a complete,
real game — working code, optimized, with **zero hallucinated or
incomplete code**.

## The studio model

- **Boss — Cyrus.** He owns the idea and the decisions. Nothing public,
  paid, or irreversible happens without his word.
- **Manager — Cyrus (the assistant).** He runs the studio day to day:
  carries the boss's answers to the agents, assigns the work, checks
  every result, and brings only verified results back to the boss.
- **Three senior agents — the specialists below.** Each has one job,
  written in its `AGENT.md` (its دستور / constitution). If a report and
  the AGENT.md disagree, the AGENT.md wins.

## The roster

| # | Agent | Folder | Job (one line) |
|---|---|---|---|
| 1 | 🎬 **The Visionary Director** | `game-director/` | Interviews the boss to extract the raw idea; designs mechanics, rules, physics, and story; writes the Game Design Document. |
| 2 | 🏗️ **The Lead Architect** | `game-architect/` | Recommends the engine (Unity, Godot, or web JS), then writes clean, modular, 100% runnable code — file by file, complete. |
| 3 | 🧪 **The QA Destroyer** | `game-qa/` | Reviews the Architect's code line by line, hunts bugs, leaks, and performance problems, runs the tests — and rejects bad work before the boss ever sees it. |

The Architect runs the house Code Agent engine and the QA Destroyer
carries the house Super Brain reviewer plus the deterministic tester —
the proven house packages, game-tuned, with one studio upgrade: their
OpenAI calls retry with backoff instead of dying on a rate limit.

## The charter — hard rules

1. **Step by step.** Never the whole game in one message. One stage at a
   time, verified before the next begins.
2. **The Director interviews FIRST.** The raw idea is extracted with
   precise questions and written into the GDD before anything is built.
   **No GDD, no code** — the Architect never codes without an approved
   roadmap.
3. **Zero hallucination.** Every fact, asset, and API is confirmed or it
   is flagged as an open question. Code must run as-is.
4. **Complete code only.** Placeholder code (`// Add logic here`, stubs,
   empty functions) is absolutely forbidden. Every function is fully
   written.
5. **The QA gate.** The QA Destroyer reviews the Architect's code line by
   line and can reject it back for fixes. The boss sees code only after
   it passes QA and the manager's review.
6. **Every report ends with the stage + the next step.** Where we are,
   and what happens next — always.

## Status

**Installed, dormant.** The Director, the Architect, and the QA
Destroyer's AI reviewer wake when the manager activates the studio (the
OpenAI key added as a GitHub repository secret — the same arrangement as
the house agents: `AGENT_API_KEY` for the Architect, `OPENAI_API_KEY`
for the reviewer). The QA tester's deterministic half needs no key and
has already passed its proof runs. **No game has been chosen yet** —
studio first, the boss's idea interview comes next.
