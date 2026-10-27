#!/usr/bin/env python3
"""CYRUS AGENTS — check_system_health.py

Live activation health check for the agent house (game studio +
house agents). Run BEFORE the teams start work:

    python3 check_system_health.py

For every service the agents use, one line is printed:

    <service> — <OK|NOT_SET|FAILED> — <detail>

  OK      a REAL minimal authenticated call succeeded just now.
  NOT_SET the environment variable is absent. Honest "not yet" —
          a warning, never a failure.
  FAILED  the variable IS set but the real call failed (HTTP
          status / error class is shown, never the key itself).

Exit code: 0 when every CONFIGURED service is OK (not-set items
are warnings), 1 when any configured service FAILED.

INFO lines (model choice, local tools) are informational only
and never affect the exit code.

Secrets are read from the environment (the repo-root .env is
loaded via python-dotenv when available). No key value is ever
printed, logged, or stored by this script.
"""

import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

TIMEOUT = 20
_failures = []


def report(service, status, detail, counts=True):
    print(f"{service} — {status} — {detail}")
    if counts and status == "FAILED":
        _failures.append(service)


def env(name):
    return (os.environ.get(name) or "").strip()


def http_json(method, url, headers=None):
    """One small HTTP call. Returns (status, parsed_json_or_None,
    error_text). Never raises."""
    req = urllib.request.Request(url, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(body), ""
            except Exception:
                return resp.status, None, "non-JSON response body"
    except urllib.error.HTTPError as exc:
        return exc.code, None, f"HTTP {exc.code}"
    except Exception as exc:  # DNS, timeout, TLS, ...
        return None, None, f"{type(exc).__name__}: {exc}"


def check_openai(service_label, var_name, purpose):
    key = env(var_name)
    if not key:
        report(service_label, "NOT_SET",
               f"{var_name} not set — {purpose} cannot run yet")
        return
    status, data, err = http_json(
        "GET", "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {key}"})
    if status == 200 and data is not None:
        n = len(data.get("data") or [])
        report(service_label, "OK",
               f"authenticated; {n} models visible")
    else:
        report(service_label, "FAILED",
               err or f"unexpected status {status}")


def check_github():
    token = env("GITHUB_TOKEN")
    if not token:
        report("GitHub (Actions agents)", "NOT_SET",
               "GITHUB_TOKEN not set locally — GitHub Actions "
               "provides it automatically in CI; needed only for "
               "local runs of the Actions-style agents")
        return
    status, data, err = http_json(
        "GET", "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"})
    if status == 200 and data is not None:
        report("GitHub (Actions agents)", "OK",
               f"authenticated as {data.get('login', '?')}")
    else:
        report("GitHub (Actions agents)", "FAILED",
               err or f"unexpected status {status}")


def info_lines():
    model = env("AGENT_MODEL")
    report("Agent model (AGENT_MODEL)", "INFO",
           f"AGENT_MODEL={model}" if model else
           "AGENT_MODEL unset — agents use their default gpt-4o",
           counts=False)
    try:
        import pygame  # noqa: F401

        report("Local tool: pygame (QA smoke runs)", "OK",
               "importable — game QA smoke runs are active",
               counts=False)
    except Exception:
        report("Local tool: pygame (QA smoke runs)", "NOT_SET",
               "not installed — QA smoke runs will SKIP honestly "
               "(never fake-pass)", counts=False)
    try:
        import dotenv  # noqa: F401

        report("Local tool: python-dotenv (.env loading)", "OK",
               "importable — .env files are loaded at entry points",
               counts=False)
    except Exception:
        report("Local tool: python-dotenv (.env loading)", "NOT_SET",
               "not installed — export variables in the shell "
               "instead (pip install -r "
               "game-team/game_creator_agents/requirements.txt)",
               counts=False)


def main():
    print("Cyrus Agents — system health check")
    print("-" * 60)
    check_openai("OpenAI via AGENT_API_KEY (game brain)",
                 "AGENT_API_KEY",
                 "the game studio (Designer/Developer), "
                 "game-architect and code-agent")
    check_openai("OpenAI via OPENAI_API_KEY (PR reviewers)",
                 "OPENAI_API_KEY",
                 "super-brain and the game-qa PR reviewer")
    check_github()
    info_lines()
    print("-" * 60)
    if _failures:
        print("RESULT: NOT READY — configured service(s) FAILED: "
              + ", ".join(_failures))
        return 1
    print("RESULT: READY — every configured service answered OK "
          "(NOT_SET items are warnings, listed above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
