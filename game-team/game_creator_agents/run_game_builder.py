"""Game Builder Pipeline — idea in, tested game code out.

Stages:
  1. DESIGN   game_designer_agent.analyze_idea  -> validated GDD (gdd.json)
  2. BUILD    game_developer_agent.generate_game -> complete project files
  3. QA       game_qa_agent.test_game            -> verdict + fix order

Any stage failure stops the chain immediately with a loud, specific error and
exit code 1. A QA rejection is a completed pipeline run whose verdict is FAIL
(exit code 1, rejection reasons printed) — the Architect's fix order.

Modes:
  Full pipeline:  python run_game_builder.py "idea text" --out game_dir
                  python run_game_builder.py --idea-file idea.txt --out game_dir
  QA only:        python run_game_builder.py --qa-only project_dir

The full pipeline writes RUN-REPORT.md inside the output directory. QA-only
mode prints the report and writes it only when --report PATH is given.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Load .env files (this folder first, then the cyrus-agents repo
# root) BEFORE the agents read AGENT_API_KEY / AGENT_MODEL. Real
# values live ONLY in those local files — never in the repo.
# Guarded: python-dotenv is declared in requirements.txt, but the
# pipeline must still start without it.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:
    pass

import game_designer_agent as designer  # noqa: E402
import game_developer_agent as developer  # noqa: E402
import game_qa_agent as qa  # noqa: E402

logger = logging.getLogger("run_game_builder")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _RunLog:
    """Stage-by-stage record of one pipeline run."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def stage(self, name: str, message: str) -> None:
        entry = f"[{_now()}] STAGE {name}: {message}"
        self.lines.append(entry)
        print(entry, flush=True)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _write_report(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
        print(f"Run report written to {path}", flush=True)
    except OSError as exc:
        logger.error("Could not write run report to %s: %s", path, exc)


def run_qa_only(project_dir: str, smoke_timeout: int, report_path: str | None) -> int:
    """QA an existing project without the LLM stages."""
    log = _RunLog()
    log.stage("QA", f"start — project: {project_dir}")
    try:
        report = qa.test_game(project_dir, smoke_timeout=smoke_timeout)
    except FileNotFoundError as exc:
        log.stage("FAILED", f"QA stage could not run: {exc}")
        print(log.text())
        return 1

    body = log.text() + "\n" + qa.format_report(report) + "\n"
    print(qa.format_report(report), flush=True)
    if report_path:
        _write_report(Path(report_path), body)
    if report.overall == qa.STATUS_PASS:
        print("PIPELINE RESULT: QA PASSED", flush=True)
        return 0
    print("PIPELINE RESULT: REJECTED BY QA — see the fix order above", flush=True)
    return 1


def run_full_pipeline(idea_text: str, out_dir: str, smoke_timeout: int) -> int:
    log = _RunLog()
    out_path = Path(out_dir)

    # ---- Stage 1: DESIGN -------------------------------------------------
    log.stage("DESIGN", "start — analysing the raw idea into a GDD")
    try:
        gdd = designer.analyze_idea(idea_text)
    except Exception as exc:  # noqa: BLE001 — pipeline must stop loudly on any stage failure
        log.stage("FAILED", f"DESIGN stage failed: {type(exc).__name__}: {exc}")
        print("PIPELINE RESULT: STOPPED at the DESIGN stage", flush=True)
        return 1
    log.stage("DESIGN", f"ok — GDD validated complete: '{gdd.title}' ({gdd.genre})")

    try:
        out_path.mkdir(parents=True, exist_ok=True)
        gdd_file = out_path / "gdd.json"
        gdd_file.write_text(
            json.dumps(asdict(gdd), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        log.stage("DESIGN", f"GDD saved to {gdd_file}")
    except OSError as exc:
        log.stage("FAILED", f"could not save the GDD into {out_path}: {exc}")
        print("PIPELINE RESULT: STOPPED at the DESIGN stage", flush=True)
        return 1

    # ---- Stage 2: BUILD --------------------------------------------------
    log.stage("BUILD", f"start — generating the project into {out_path}")
    try:
        written = developer.generate_game(gdd, out_path)
    except Exception as exc:  # noqa: BLE001
        log.stage("FAILED", f"BUILD stage failed: {type(exc).__name__}: {exc}")
        _write_report(out_path / "RUN-REPORT.md", log.text())
        print("PIPELINE RESULT: STOPPED at the BUILD stage", flush=True)
        return 1
    log.stage("BUILD", f"ok — {len(written)} files written: "
              + ", ".join(path.name for path in written))

    # ---- Stage 3: QA ------------------------------------------------------
    log.stage("QA", "start — deterministic QA on the generated project")
    try:
        report = qa.test_game(out_path, smoke_timeout=smoke_timeout)
    except Exception as exc:  # noqa: BLE001
        log.stage("FAILED", f"QA stage could not run: {type(exc).__name__}: {exc}")
        _write_report(out_path / "RUN-REPORT.md", log.text())
        print("PIPELINE RESULT: STOPPED at the QA stage", flush=True)
        return 1
    log.stage("QA", f"verdict: {report.overall} ({len(report.rejected)} rejections)")
    print(qa.format_report(report), flush=True)

    _write_report(
        out_path / "RUN-REPORT.md", log.text() + "\n" + qa.format_report(report) + "\n"
    )
    if report.overall == qa.STATUS_PASS:
        print("PIPELINE RESULT: GAME BUILT AND QA PASSED", flush=True)
        return 0
    print("PIPELINE RESULT: GAME BUILT BUT REJECTED BY QA — fix order is in the report",
          flush=True)
    return 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        description="Game builder pipeline: idea -> GDD -> game code -> QA verdict."
    )
    parser.add_argument("idea", nargs="?", help="The raw game idea text")
    parser.add_argument("--idea-file", help="Read the idea text from this file")
    parser.add_argument("--out", help="Output directory for the generated game (full pipeline)")
    parser.add_argument("--qa-only", metavar="PROJECT_DIR",
                        help="Skip the LLM stages; run QA on an existing project")
    parser.add_argument("--report", help="In --qa-only mode, also write the report to this path")
    parser.add_argument("--timeout", type=int, default=qa.DEFAULT_SMOKE_TIMEOUT,
                        help=f"Smoke-run timeout in seconds (default {qa.DEFAULT_SMOKE_TIMEOUT})")
    args = parser.parse_args(argv)

    if args.qa_only:
        return run_qa_only(args.qa_only, args.timeout, args.report)

    idea_text = args.idea or ""
    if args.idea_file:
        try:
            idea_text = Path(args.idea_file).read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Could not read idea file %s: %s", args.idea_file, exc)
            return 2
    if not idea_text.strip():
        parser.error("a game idea is required (positional text or --idea-file), "
                     "or use --qa-only PROJECT_DIR")
    if not args.out:
        parser.error("--out is required for the full pipeline")

    return run_full_pipeline(idea_text, args.out, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
