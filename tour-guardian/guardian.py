#!/usr/bin/env python3
"""Tour Guardian — read-only health checks for Victoria Tour and Adventure.

Performs the 7 checks defined in AGENT.md, prints one PASS/FAIL line per
check with evidence (HTTP status + bytes), and writes the run report to
memory/runs/<YYYY-MM-DD>.md and memory/last-run.md next to this script.

Read-only forever: this script only ever sends HTTP GET requests.
Standard library only (urllib) — no pip installs.

Exit code: 0 when every check passes, 1 when any check fails.
"""

import http.client
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

TIMEOUT_SECONDS = 20
USER_AGENT = "CyrusTourGuardian/1.0 (read-only health check)"
MIN_WIDGET_BYTES = 2000

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"
RUNS_DIR = MEMORY_DIR / "runs"


def is_200(status, size):
    return status == 200


def is_not_5xx(status, size):
    return status is not None and status < 500


def is_widget_ok(status, size):
    return status == 200 and size >= MIN_WIDGET_BYTES


# (name, url, pass_rule, rule_description)
CHECKS = [
    (
        "Main site",
        "https://victoriatourandadventure.com",
        is_200,
        "HTTP 200",
    ),
    (
        "App site",
        "https://app.victoriatourandadventure.com",
        is_200,
        "HTTP 200",
    ),
    (
        "App API devices.php",
        "https://app.victoriatourandadventure.com/api/devices.php",
        is_not_5xx,
        "responds, not 5xx",
    ),
    (
        "App API consent.php",
        "https://app.victoriatourandadventure.com/api/consent.php",
        is_not_5xx,
        "responds, not 5xx",
    ),
    (
        "Chat widget JS",
        "https://app.victoriatourandadventure.com/js/vta-chat-widget-premium.js",
        is_widget_ok,
        f"HTTP 200 and >= {MIN_WIDGET_BYTES} bytes",
    ),
    (
        "IELTS Academy site (cyrusielts.com)",
        "https://cyrusielts.com",
        is_200,
        "HTTP 200",
    ),
    (
        "IELTS Academy style.css",
        "https://cyrusielts.com/style.css",
        is_200,
        "HTTP 200",
    ),
]


def fetch(url):
    """GET the URL and return (status, body, error).

    Primary engine: curl. Manager's finding (Cyrus, 2026-10-26): from this
    network, urllib reads against the Hostinger CDN intermittently truncate
    mid-body (IncompleteRead, wildly varying byte counts) while curl
    delivers the exact full body for the same URLs every time. The urllib
    path below stays as a fallback for machines without curl.
    """
    try:
        proc = subprocess.run(
            [
                "curl", "-sS", "-L",
                "--max-time", str(TIMEOUT_SECONDS),
                "-A", USER_AGENT,
                "-H", "Accept-Encoding: identity",
                "-w", "\n__STATUS__:%{http_code}",
                url,
            ],
            capture_output=True,
            timeout=TIMEOUT_SECONDS + 10,
        )
        out = proc.stdout or b""
        marker = b"\n__STATUS__:"
        idx = out.rfind(marker)
        if idx == -1:
            detail = (proc.stderr or b"").decode("utf-8", "replace").strip()[:160]
            return None, b"", f"curl: no status returned (rc={proc.returncode}) {detail}"
        status = int(out[idx + len(marker):].strip())
        body = out[:idx]
        if proc.returncode != 0 and not body:
            detail = (proc.stderr or b"").decode("utf-8", "replace").strip()[:160]
            return status or None, body, f"curl rc={proc.returncode}: {detail}"
        return status, body, ""
    except FileNotFoundError:
        return _fetch_urllib(url)
    except Exception as exc:
        return None, b"", f"{type(exc).__name__}: {exc}"


def _fetch_urllib(url):
    """urllib fallback: chunked read, IncompleteRead keeps the partial body."""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as resp:
            status = resp.status
            chunks = []
            try:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
            except http.client.IncompleteRead as exc:
                if exc.partial:
                    chunks.append(exc.partial)
            return status, b"".join(chunks), ""
    except urllib.error.HTTPError as exc:
        # The server answered; an HTTP error status is still evidence.
        try:
            body = exc.read()
        except Exception:
            body = b""
        return exc.code, body, ""
    except Exception as exc:  # timeout, DNS, TLS, connection refused...
        return None, b"", f"{type(exc).__name__}: {exc}"


def fetch_with_retry(url, attempts=3):
    """Fetch with retries for transient CDN stream cuts.

    The Hostinger CDN intermittently closes a stream early (the same URL can
    pass one minute and truncate the next). A single attempt is not honest
    evidence either way, so: retry on transport errors and on HTTP 200 with
    an empty body, and keep the attempt that delivered the most bytes.
    """
    best = (None, b"", "no attempt made")
    for _ in range(attempts):
        status, body, error = fetch(url)
        if len(body) > len(best[1]):
            best = (status, body, error)
        if not error and not (status == 200 and len(body) == 0):
            return status, body, error
    return best


def run_check(name, url, rule, rule_desc):
    """GET the URL (with retries) and judge it by the rule. Never raises."""
    status, body, error = fetch_with_retry(url)
    size = len(body)

    passed = False if error else bool(rule(status, size))
    return {
        "name": name,
        "url": url,
        "rule": rule_desc,
        "passed": passed,
        "status": status,
        "size": size,
        "error": error,
    }


def format_line(index, result):
    verdict = "PASS" if result["passed"] else "FAIL"
    if result["error"]:
        evidence = f"no response ({result['error']})"
    else:
        evidence = f"HTTP {result['status']}, {result['size']} bytes"
    return f"{verdict} {index}. {result['name']} — {evidence}"


def build_report(now, results):
    passed_count = sum(1 for r in results if r["passed"])
    overall = "ALL PASS" if passed_count == len(results) else "FAILURES PRESENT"
    lines = [
        f"# Tour Guardian run — {now.strftime('%Y-%m-%d %H:%M:%S %Z')}".rstrip(),
        "",
        f"Overall: **{overall}** ({passed_count}/{len(results)} checks passed)",
        "",
        "| # | Check | Target | Rule | Result | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        verdict = "PASS" if r["passed"] else "FAIL"
        evidence = (
            f"no response ({r['error']})"
            if r["error"]
            else f"HTTP {r['status']}, {r['size']} bytes"
        )
        lines.append(
            f"| {i} | {r['name']} | {r['url']} | {r['rule']} | {verdict} | {evidence} |"
        )
    lines += [
        "",
        "Read-only run: GET requests only, nothing was changed.",
        "Failures are reported to the manager; the Guardian never fixes anything itself.",
        "",
    ]
    return "\n".join(lines)


def main():
    now = datetime.now().astimezone()
    results = [run_check(*check) for check in CHECKS]

    for i, r in enumerate(results, 1):
        print(format_line(i, r))
    passed_count = sum(1 for r in results if r["passed"])
    overall = "ALL PASS" if passed_count == len(results) else "FAILURES PRESENT"
    print(f"OVERALL: {overall} ({passed_count}/{len(results)})")

    report = build_report(now, results)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    dated_path = RUNS_DIR / f"{now.strftime('%Y-%m-%d')}.md"
    dated_path.write_text(report, encoding="utf-8")
    (MEMORY_DIR / "last-run.md").write_text(report, encoding="utf-8")
    print(f"Report written: {dated_path} and {MEMORY_DIR / 'last-run.md'}")

    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
