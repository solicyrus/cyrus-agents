#!/usr/bin/env python3
"""Game Tester — deterministic checks for a game project folder.

Detects and runs whatever checks a project actually has (see AGENT.md):

  1. pytest           — if pytest test files exist and pytest is importable
  2. npm test         — if package.json defines a real test script
  3. Python syntax    — py_compile pass over every .py file in the project
  4. Godot headless   — only if a `godot` binary is on PATH and the project
                        has a project.godot file

Every check ends as PASS, FAIL, or SKIP. A check that could not run is a
SKIP with the reason — never a PASS. The tester is read-only: it never
edits the project and never fixes anything. It reports; the manager
decides.

Usage: python3 tester.py [PROJECT_DIR]   (default: current directory)

Writes the run report to memory/runs/<YYYY-MM-DD-HHMMSS>.md next to this
script and refreshes memory/last-run.md.

Exit code: 0 when every check that ran passed, 1 when any check failed.
Standard library only — no pip installs.
"""

import importlib.util
import json
import py_compile
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"
RUNS_DIR = MEMORY_DIR / "runs"

PYTEST_TIMEOUT = 180
NPM_TIMEOUT = 180
GODOT_TIMEOUT = 120

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox"}


def find_files(project, predicate):
    """All files under project matching predicate(path), skipping junk dirs."""
    found = []
    for path in sorted(project.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and predicate(path):
            found.append(path)
    return found


def run_command(argv, cwd, timeout):
    """Run a command, return (exit_code, combined_output). Never raises."""
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout} seconds"
    except Exception as exc:  # missing binary, OS error...
        return None, f"{type(exc).__name__}: {exc}"


def tail(text, limit=400):
    """Last chunk of output, flattened for a one-cell evidence string."""
    text = " ".join(text.strip().split())
    if len(text) > limit:
        text = "..." + text[-limit:]
    return text or "(no output)"


def check_pytest(project):
    tests = find_files(
        project,
        lambda p: p.name.startswith("test_") and p.suffix == ".py"
        or p.name.endswith("_test.py"),
    )
    if not tests:
        return ("SKIP", "no pytest test files (test_*.py / *_test.py) found")
    if importlib.util.find_spec("pytest") is None:
        return ("SKIP", f"{len(tests)} test file(s) found but pytest is not installed")
    code, out = run_command(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(project)],
        project,
        PYTEST_TIMEOUT,
    )
    if code is None:
        return ("FAIL", f"pytest could not run: {tail(out)}")
    if code == 5:
        return ("SKIP", "pytest collected no tests")
    if code == 0:
        return ("PASS", f"pytest exit 0 — {tail(out, 200)}")
    return ("FAIL", f"pytest exit {code} — {tail(out)}")


def check_npm_test(project):
    package_json = project / "package.json"
    if not package_json.exists():
        return ("SKIP", "no package.json")
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception as exc:
        return ("FAIL", f"package.json is not valid JSON: {exc}")
    script = (data.get("scripts") or {}).get("test", "")
    if not script or "no test specified" in script:
        return ("SKIP", "package.json has no real test script")
    if shutil.which("npm") is None:
        return ("SKIP", "test script exists but npm is not on PATH")
    code, out = run_command(["npm", "test", "--silent"], project, NPM_TIMEOUT)
    if code is None:
        return ("FAIL", f"npm test could not run: {tail(out)}")
    if code == 0:
        return ("PASS", f"npm test exit 0 — {tail(out, 200)}")
    return ("FAIL", f"npm test exit {code} — {tail(out)}")


def check_python_syntax(project):
    py_files = find_files(project, lambda p: p.suffix == ".py")
    if not py_files:
        return ("SKIP", "no .py files in the project")
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, path in enumerate(py_files):
            try:
                py_compile.compile(
                    str(path), cfile=str(Path(tmp) / f"c{i}.pyc"), doraise=True
                )
            except py_compile.PyCompileError as exc:
                errors.append(f"{path.relative_to(project)}: {exc.msg.strip()}")
            except Exception as exc:
                errors.append(f"{path.relative_to(project)}: {type(exc).__name__}: {exc}")
    if errors:
        return ("FAIL", f"{len(errors)} of {len(py_files)} file(s) failed: " + "; ".join(errors)[:400])
    return ("PASS", f"all {len(py_files)} .py file(s) compile cleanly")


def check_godot(project):
    godot = shutil.which("godot")
    if godot is None:
        return ("SKIP", "godot is not on PATH")
    if not (project / "project.godot").exists():
        return ("SKIP", "godot found but the project has no project.godot")
    code, out = run_command(
        [godot, "--headless", "--check-only", "--quit", "--path", str(project)],
        project,
        GODOT_TIMEOUT,
    )
    if code is None:
        return ("FAIL", f"godot check could not run: {tail(out)}")
    if code == 0:
        return ("PASS", "godot --headless --check-only exit 0")
    return ("FAIL", f"godot exit {code} — {tail(out)}")


CHECKS = [
    ("pytest", check_pytest),
    ("npm test", check_npm_test),
    ("Python syntax compile", check_python_syntax),
    ("Godot headless check", check_godot),
]


def build_report(now, project, results):
    ran = [r for r in results if r[1] != "SKIP"]
    failed = [r for r in results if r[1] == "FAIL"]
    if not ran:
        overall = "NO CHECKS RAN (all skipped)"
    elif failed:
        overall = f"FAILURES PRESENT ({len(failed)} failed, {len(ran)} ran, {len(results) - len(ran)} skipped)"
    else:
        overall = f"ALL PASS ({len(ran)} ran, {len(results) - len(ran)} skipped)"
    lines = [
        f"# Game Tester run — {now.strftime('%Y-%m-%d %H:%M:%S %Z')}".rstrip(),
        "",
        f"Project: `{project}`",
        f"Overall: **{overall}**",
        "",
        "| # | Check | Result | Evidence |",
        "|---|---|---|---|",
    ]
    for i, (name, verdict, evidence) in enumerate(results, 1):
        cell = evidence.replace("|", "/")
        lines.append(f"| {i} | {name} | {verdict} | {cell} |")
    lines += [
        "",
        "Read-only run: checks were executed, nothing in the project was changed.",
        "The Game Tester never fixes anything; failures go to the manager.",
        "",
    ]
    return "\n".join(lines), overall, bool(failed)


def main(argv):
    project = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    if not project.is_dir():
        print(f"ERROR: project folder not found: {project}")
        return 2

    now = datetime.now().astimezone()
    results = []
    for name, fn in CHECKS:
        verdict, evidence = fn(project)
        results.append((name, verdict, evidence))
        print(f"{verdict} {name} — {evidence}")

    report, overall, any_failed = build_report(now, project, results)
    print(f"OVERALL: {overall}")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUNS_DIR / f"{now.strftime('%Y-%m-%d-%H%M%S')}.md"
    run_path.write_text(report, encoding="utf-8")
    (MEMORY_DIR / "last-run.md").write_text(report, encoding="utf-8")
    print(f"Report written: {run_path} and {MEMORY_DIR / 'last-run.md'}")

    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
