# Agent: Super Brain (PR Reviewer)

**Source:** Package written by Gemini Pro, sent by Cyrus 2026-10-26, checked and installed by the manager.

## Job
When a Pull Request is opened or updated in this repository, read the changed files,
send the diff to GPT-4o with the review brief inside `ai_pr_reviewer.py`
(security / performance / architecture / code quality), and post the result as a
comment on the Pull Request.

## Files
- `ai_pr_reviewer.py` — the agent itself (as received).
- `requirements.txt` — PyGithub + openai (as received).
- `../../.github/workflows/pr-reviewer.yml` — the wake-up motor (GitHub Actions).
  Manager's adaptation: the workflow points at `super-brain/` paths because this
  agent lives in the cyrus-agents house, not at a repo root. Nothing else changed.

## Honest limits
- It REVIEWS code and posts comments. It does not write or fix code.
- Every review costs a GPT-4o call on Cyrus's OpenAI credit.
- It only wakes for Pull Requests in THIS repository (cyrus-agents).

## To activate
Add the repository secret `OPENAI_API_KEY` (Settings → Secrets and variables →
Actions). Until that secret exists, the workflow runs but the agent reports the
missing key and stops — by design.
