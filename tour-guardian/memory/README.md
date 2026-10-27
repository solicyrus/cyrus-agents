# Tour Guardian — memory

This folder is the Tour Guardian's memory: the written record of every run.

- `runs/<YYYY-MM-DD>.md` — one report file per day, holding that day's run:
  the time, all 5 checks with their PASS/FAIL result, the HTTP status code
  and response size for each, and the overall verdict.
- `last-run.md` — always a copy of the newest run report, so the manager can
  see the Guardian's current state in one file.

Reports are written by `guardian.py` on every run and are never edited by
hand. A FAIL in these files is a fact, not an embarrassment — it is the
Guardian doing its job.
