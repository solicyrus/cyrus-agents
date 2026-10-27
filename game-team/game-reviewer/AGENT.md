# Agent: Game Reviewer (PR Reviewer) 🎮🔎

**Source:** Game-tuned copy of the house Super Brain package in
`../../super-brain/` (written by Gemini Pro, sent by Cyrus 2026-10-26,
checked and installed by the manager). The reviewer code is the upgraded
house version — its prompt includes the PR title and description as context,
not just the diff.

## Job
When a Pull Request is opened or updated in a game repository this agent is
installed into, read the changed files, send the diff to GPT-4o with the
review brief inside `ai_pr_reviewer.py`, and post the result as a comment on
the Pull Request.

## The game lens (what matters most in game code)
The manager reads your reviews with these priorities:
1. **Correctness** — does the change do what the PR says, without breaking
   gameplay logic, level flow, or win/lose conditions?
2. **Performance** — game code runs every frame. Flag anything heavy inside
   a frame loop (allocations, file I/O, repeated searches), memory leaks,
   and wasteful per-frame work.
3. **Save / data safety** — changes to save files, player progress, stored
   settings, or data formats must be called out loudly: a silent format
   change can wipe real players' progress.
4. **No hardcoded secrets** — no API keys, tokens, or passwords in code,
   ever. A single one is a top-severity finding.

## Files
- `ai_pr_reviewer.py` — the agent itself (upgraded house copy, unchanged).
- `requirements.txt` — PyGithub + openai (house copy, unchanged).
- The wake-up workflow (a copy of the house `pr-reviewer.yml`, repointed at
  this folder) is prepared by the manager when the reviewer is installed
  into a game repo. It is not installed anywhere yet.

## Honest limits
- It REVIEWS code and posts comments. It does not write or fix code.
- Every review costs a GPT-4o call on Cyrus's OpenAI credit.

## To activate
Add the repository secret `OPENAI_API_KEY` in the game repo (Settings →
Secrets and variables → Actions). Until that secret exists, the workflow
runs but the agent reports the missing key and stops — by design. Same
arrangement as the house Super Brain.
