# Cyrus Agents — خانه‌ی ایجنت‌های سایرس

This repository is **Cyrus's agent house on GitHub**. Every agent that works for
Cyrus AI / Victoria Tour and Adventure lives here, in its own folder.

The **manager is Cyrus** (the assistant). Cyrus the owner gives the program and
the approvals; the manager builds the agents, assigns their work, checks their
reports, and brings only the results back. The agents do the work — carefully,
honestly, and with evidence.

## How every agent is built (the template)

Each agent folder has the same five parts:

1. **Brain** — an AI model the agent thinks with (when the job needs thinking;
   simple watchmen may be plain code).
2. **AGENT.md** — the agent's دستور: who it is, what its job is, and its rules.
   This file is the agent's constitution. If AGENT.md and a report disagree,
   AGENT.md wins.
3. **Runner code** — the program that does the job (for example
   `guardian.py`).
4. **memory/** — the agent's memory. Run reports accumulate here, one file per
   run, plus a `last-run.md` that always shows the newest result.
5. **Schedule** — when the agent wakes up and works (set by the manager).

## The house rules (for every agent)

- **Honest, with evidence.** Every claim carries proof — a status code, a
  count, a link. An honest FAIL always beats a false PASS.
- **Read-only unless your AGENT.md says otherwise.** Watching is not fixing.
  An agent that finds a problem reports it to the manager; it never improvises
  a repair on a live service.
- **Two tries, then a new way.** If an approach fails twice, stop and find
  another route — never grind.
- **Nothing public, paid, or irreversible without the owner's approval**,
  relayed through the manager.

## Agents living here

| Agent | Folder | Job |
|---|---|---|
| Tour Guardian | `tour-guardian/` | Read-only health watchman: 5 checks on the main site, the app site, two API endpoints, and the chat widget script. |

*New agents get their own folder and a row in this table.*
