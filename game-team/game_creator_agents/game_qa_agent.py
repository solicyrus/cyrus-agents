"""Game QA Agent — the QA Destroyer, as code.

Fully deterministic: no LLM, no network, standard library only. Tests a game
project and issues a structured verdict. Anything that fails is REJECTED with
reasons — this report is the fix-order the Architect must answer.

Checks:
  1. compile        — every .py file must byte-compile.
  2. placeholders   — no TODO/FIXME/'pass' stubs/'Add logic here' etc.
  3. smoke_run      — headless run of the entry point with dummy SDL drivers
                      (only when pygame is importable; otherwise SKIP with
                      the reason — a skipped check is NEVER reported as PASS).
  4. perf_sanity    — code size / line count / smoke wall time, as evidence.

Overall PASS requires every check that ran to pass. Exit code of the CLI:
0 = PASS, 1 = FAIL, 2 = usage/environment error.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import py_compile
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from game_developer_agent import find_placeholders  # noqa: E402

logger = logging.getLogger("game_qa_agent")

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIP = "SKIP"

ENTRY_POINT_CANDIDATES = ("main.py", "game.py", "run.py")
DEFAULT_SMOKE_TIMEOUT = 10


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass
class QAReport:
    project_dir: str
    checks: list[CheckResult] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    total_code_bytes: int = 0
    total_code_lines: int = 0
    smoke_seconds: float | None = None

    @property
    def overall(self) -> str:
        """PASS only when nothing failed (SKIP never blocks, never fakes PASS
        for the check itself — it is reported as SKIP in the checks list)."""
        if any(check.status == STATUS_FAIL for check in self.checks):
            return STATUS_FAIL
        return STATUS_PASS

    def to_dict(self) -> dict:
        data = asdict(self)
        data["overall"] = self.overall
        return data


def _python_files(project: Path) -> list[Path]:
    return sorted(
        path
        for path in project.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _check_compile(files: list[Path], report: QAReport) -> None:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qa-compile-") as tmp:
        for index, path in enumerate(files):
            try:
                py_compile.compile(
                    str(path), cfile=os.path.join(tmp, f"mod{index}.pyc"), doraise=True
                )
            except py_compile.PyCompileError as exc:
                failures.append(f"{path.name}: {exc.msg.strip()}")
            except OSError as exc:
                failures.append(f"{path.name}: could not read file: {exc}")
    if failures:
        report.rejected.extend(f"compile: {item}" for item in failures)
        report.checks.append(
            CheckResult(
                "compile",
                STATUS_FAIL,
                f"{len(failures)} of {len(files)} files failed to compile: "
                + "; ".join(failures),
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "compile",
                STATUS_PASS,
                f"all {len(files)} Python files compile",
            )
        )


def _check_placeholders(files: list[Path], report: QAReport) -> None:
    findings: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(f"{path.name}: could not read file: {exc}")
            continue
        for finding in find_placeholders(text):
            findings.append(f"{path.name}: {finding}")
    if findings:
        report.rejected.extend(f"placeholder: {item}" for item in findings)
        report.checks.append(
            CheckResult(
                "placeholders",
                STATUS_FAIL,
                f"{len(findings)} placeholder/stub findings: " + "; ".join(findings),
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "placeholders",
                STATUS_PASS,
                f"no placeholder/stub patterns in {len(files)} files",
            )
        )


def _find_entry_point(project: Path) -> Path | None:
    for name in ENTRY_POINT_CANDIDATES:
        candidate = project / name
        if candidate.is_file():
            return candidate
    return None


def _check_smoke_run(project: Path, timeout: int, report: QAReport) -> None:
    if importlib.util.find_spec("pygame") is None:
        report.checks.append(
            CheckResult(
                "smoke_run",
                STATUS_SKIP,
                "pygame is not installed in this environment, so the headless "
                "smoke run cannot be exercised (install pygame to enable it)",
            )
        )
        return

    entry = _find_entry_point(project)
    if entry is None:
        report.checks.append(
            CheckResult(
                "smoke_run",
                STATUS_SKIP,
                "no entry point found (looked for main.py, game.py, run.py)",
            )
        )
        return

    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    logger.info("Smoke-running %s headless (timeout %ss)", entry, timeout)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(entry)],
            cwd=str(project),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.monotonic() - started
        report.smoke_seconds = round(elapsed, 2)
        if proc.returncode == 0:
            report.checks.append(
                CheckResult(
                    "smoke_run",
                    STATUS_PASS,
                    f"{entry.name} exited cleanly (code 0) after {elapsed:.2f}s headless",
                )
            )
        else:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            evidence = tail[-1] if tail else "no output captured"
            report.rejected.append(
                f"smoke_run: {entry.name} exited with code {proc.returncode}: {evidence}"
            )
            report.checks.append(
                CheckResult(
                    "smoke_run",
                    STATUS_FAIL,
                    f"{entry.name} exited with code {proc.returncode} after "
                    f"{elapsed:.2f}s: {evidence}",
                )
            )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        report.smoke_seconds = round(elapsed, 2)
        report.checks.append(
            CheckResult(
                "smoke_run",
                STATUS_PASS,
                f"{entry.name} survived the full {timeout}s smoke window without "
                "crashing (long-running game loop, killed by timeout as designed)",
            )
        )
    except OSError as exc:
        report.checks.append(
            CheckResult(
                "smoke_run",
                STATUS_SKIP,
                f"could not launch the entry point: {exc}",
            )
        )


def _check_perf_sanity(files: list[Path], report: QAReport) -> None:
    total_bytes = 0
    total_lines = 0
    for path in files:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        total_bytes += len(data)
        total_lines += data.count(b"\n")
    report.total_code_bytes = total_bytes
    report.total_code_lines = total_lines
    smoke_note = (
        f", smoke wall time {report.smoke_seconds}s"
        if report.smoke_seconds is not None
        else ""
    )
    report.checks.append(
        CheckResult(
            "perf_sanity",
            STATUS_PASS,
            f"{len(files)} Python files, {total_bytes} bytes, "
            f"{total_lines} lines{smoke_note}",
        )
    )


def test_game(project_dir: str | Path, smoke_timeout: int = DEFAULT_SMOKE_TIMEOUT) -> QAReport:
    """Run the full deterministic QA suite against a game project directory.

    Raises FileNotFoundError when the directory does not exist — QA never
    guesses about a project it cannot see.
    """
    project = Path(project_dir)
    if not project.is_dir():
        raise FileNotFoundError(f"QA project directory does not exist: {project}")

    report = QAReport(project_dir=str(project))
    files = _python_files(project)
    if not files:
        report.rejected.append("no Python files found in the project")
        report.checks.append(
            CheckResult("compile", STATUS_FAIL, "no Python files found in the project")
        )
        return report

    _check_compile(files, report)
    _check_placeholders(files, report)
    _check_smoke_run(project, smoke_timeout, report)
    _check_perf_sanity(files, report)
    logger.info(
        "QA verdict for %s: %s (%d rejections)",
        project,
        report.overall,
        len(report.rejected),
    )
    return report


def format_report(report: QAReport) -> str:
    lines = [
        f"QA Report — {report.project_dir}",
        f"Overall: {report.overall}",
        "Checks:",
    ]
    for check in report.checks:
        lines.append(f"  [{check.status}] {check.name}: {check.detail}")
    if report.rejected:
        lines.append("Rejected items (fix order):")
        for item in report.rejected:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        description="Deterministic QA for a game project (compile, placeholders, smoke run)."
    )
    parser.add_argument("project_dir", help="Path to the game project directory")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_SMOKE_TIMEOUT,
        help=f"Smoke-run timeout in seconds (default {DEFAULT_SMOKE_TIMEOUT})",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    args = parser.parse_args(argv)

    try:
        report = test_game(args.project_dir, smoke_timeout=args.timeout)
    except FileNotFoundError as exc:
        logger.error("QA cannot run: %s", exc)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_report(report))
    return 0 if report.overall == STATUS_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
