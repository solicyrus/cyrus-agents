"""Game Developer Agent — the Lead Architect, as code.

Generates a complete, modular game project from a validated GDD: one LLM call
per module, each module checked before anything is written to disk.

Studio red lines enforced here, deterministically:
  * Placeholder guard: any generated file containing TODO/FIXME markers, a bare
    ``pass`` stub, "Add logic here", a raised NotImplementedError, etc. is
    REJECTED and generate_game raises — the file never reaches disk.
  * Syntax guard: any generated file that does not compile is rejected.
  * Honesty: no AGENT_API_KEY -> AgentNotConfiguredError. No fake code, ever.

Environment:
  AGENT_API_KEY  OpenAI API key (required for generate_game).
  AGENT_MODEL    Model name (default "gpt-4o").
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("game_developer_agent")

# Load .env files (this folder first, then the cyrus-agents repo
# root) so AGENT_API_KEY / AGENT_MODEL can live in a local,
# never-committed .env. Guarded: python-dotenv is declared in
# requirements.txt, but this module must import cleanly without it.
try:
    from dotenv import load_dotenv

    _here = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_here, ".env"))
    load_dotenv(os.path.join(_here, "..", "..", ".env"))
except Exception:
    pass

RETRY_DELAYS = (2, 5)
DEFAULT_MODEL = "gpt-4o"


class AgentNotConfiguredError(RuntimeError):
    """Raised when the agent cannot run because its environment is incomplete."""


class CodeRejectedError(RuntimeError):
    """Raised when generated code trips the placeholder or syntax guard."""


# ---------------------------------------------------------------------------
# Placeholder guard (deterministic; shared with the QA agent)
# ---------------------------------------------------------------------------

_PLACEHOLDER_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TODO marker", re.compile(r"\bTODO\b")),
    ("FIXME marker", re.compile(r"\bFIXME\b")),
    ("'Add logic here' placeholder", re.compile(r"add logic here", re.IGNORECASE)),
    ("'implement later' placeholder", re.compile(r"implement (this|it|later)\b", re.IGNORECASE)),
    ("'your code here' placeholder", re.compile(r"your code here", re.IGNORECASE)),
    ("generic 'placeholder' marker", re.compile(r"\bplaceholder\b", re.IGNORECASE)),
    ("NotImplementedError stub", re.compile(r"raise\s+NotImplementedError")),
    ("bare 'pass' stub line", re.compile(r"^\s*pass\s*$")),
    ("'pass' stub with trailing comment", re.compile(r"^\s*pass\s*#")),
    ("ellipsis '...' stub body", re.compile(r"^\s*\.\.\.\s*$")),
)


def find_placeholders(code_text: str) -> list[str]:
    """Scan code text for placeholder/stub patterns.

    Returns one human-readable finding per hit, e.g. "line 12: TODO marker".
    An empty list means the code is clean of known stub patterns.
    """
    findings: list[str] = []
    for lineno, line in enumerate(code_text.splitlines(), start=1):
        for label, pattern in _PLACEHOLDER_RULES:
            if pattern.search(line):
                findings.append(f"line {lineno}: {label}: {line.strip()[:80]!r}")
    return findings


# ---------------------------------------------------------------------------
# LLM plumbing (same retry policy as the rest of the game wing)
# ---------------------------------------------------------------------------

def _get_openai_client():
    api_key = os.environ.get("AGENT_API_KEY", "").strip()
    if not api_key:
        raise AgentNotConfiguredError(
            "AGENT_API_KEY not configured: set the AGENT_API_KEY environment "
            "variable (or GitHub secret) before running the developer agent. "
            "Refusing to fabricate game code without the LLM."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AgentNotConfiguredError(
            "The 'openai' Python package is not installed in this environment; "
            "install the game wing requirements before running the developer agent."
        ) from exc
    return OpenAI(api_key=api_key)


def _create_with_retry(client, **kwargs):
    """client.chat.completions.create with retry + exponential backoff
    (transient failures only: rate limit, connection, timeout, 429/5xx)."""
    from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            return client.chat.completions.create(**kwargs)
        except (RateLimitError, APIConnectionError, APITimeoutError) as exc:
            last_exc = exc
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            if status is not None and (status == 429 or status >= 500):
                last_exc = exc
            else:
                raise
        if attempt < 2:
            delay = RETRY_DELAYS[attempt]
            logger.warning(
                "OpenAI call failed (attempt %d/3): %s. Retrying in %ss...",
                attempt + 1,
                last_exc,
                delay,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("OpenAI call failed without an exception (unreachable)")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

# The module plan for a standard Pygame project, generated one file per call.
PYGAME_MODULE_PLAN: tuple[tuple[str, str], ...] = (
    (
        "config.py",
        "All constants and tuning values for the game: window size, FPS, colours, "
        "speeds, scoring values, physics constants taken from the GDD. No logic.",
    ),
    (
        "entities.py",
        "The game's entity classes (player, enemies/objects, pickups as the GDD "
        "requires) with complete update/draw behaviour driven by config.py.",
    ),
    (
        "main.py",
        "The entry point: initialises the engine, runs the main game loop "
        "(events -> update -> draw), applies the GDD physics and scoring, shows "
        "the score, handles win/lose states and a clean quit. Imports config and "
        "entities. Must be runnable as `python main.py`.",
    ),
)


def _gdd_to_dict(gdd: Any) -> dict[str, Any]:
    if isinstance(gdd, Mapping):
        return dict(gdd)
    if is_dataclass(gdd) and not isinstance(gdd, type):
        return asdict(gdd)
    if hasattr(gdd, "__dict__"):
        return dict(vars(gdd))
    raise TypeError(
        f"generate_game expects a GDD dict or dataclass, got {type(gdd).__name__}"
    )


def _detect_engine(gdd: dict[str, Any]) -> str:
    """The engine named by the GDD wins; Pygame is the studio default."""
    for key in ("engine", "platform", "genre"):
        value = str(gdd.get(key, "")).lower()
        if "pygame" in value:
            return "pygame"
        if "godot" in value:
            return "godot"
        if "javascript" in value or "web" in value or "html5" in value:
            return "javascript"
    return "pygame"


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        kept = [line for line in lines if not line.strip().startswith("```")]
        stripped = "\n".join(kept).strip()
    return stripped + "\n"


def _request_module_code(
    client,
    model: str,
    gdd: dict[str, Any],
    filename: str,
    role: str,
    already_generated: list[str],
) -> str:
    gdd_json = json.dumps(gdd, indent=2, ensure_ascii=False)
    done_note = (
        "Modules already generated (import from them, do not redefine them): "
        + ", ".join(already_generated)
        if already_generated
        else "This is the first module; no other project modules exist yet."
    )
    system = (
        "You are the Lead Architect of a game studio: a senior Python game "
        "developer. Write ONE complete, runnable module of a Pygame game. "
        "Reply with the module's Python source code ONLY — no markdown fences, "
        "no explanations. Hard rules: every function and method fully "
        "implemented; NO TODO/FIXME comments, NO bare 'pass' stubs, NO "
        "'...' bodies, NO NotImplementedError, NO placeholder text of any "
        "kind; the file must compile exactly as written and implement the "
        "GDD faithfully (mechanics, physics rules, scoring, controls, "
        "win/lose conditions)."
    )
    user = (
        f"Game Design Document:\n{gdd_json}\n\n"
        f"Module to write now: {filename}\nRole of this module: {role}\n{done_note}"
    )
    response = _create_with_retry(
        client,
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise CodeRejectedError(
            f"LLM returned empty code for module {filename}; rejecting the run"
        )
    return _strip_code_fences(content)


def _validate_module(filename: str, code_text: str) -> None:
    """Reject a generated module that trips the placeholder or syntax guard."""
    findings = find_placeholders(code_text)
    if findings:
        raise CodeRejectedError(
            f"Generated module {filename} REJECTED by the placeholder guard: "
            + "; ".join(findings)
        )
    try:
        compile(code_text, filename, "exec")
    except SyntaxError as exc:
        raise CodeRejectedError(
            f"Generated module {filename} REJECTED: does not compile: {exc}"
        ) from exc


def generate_game(gdd: Any, out_dir: str | Path) -> list[Path]:
    """Generate a complete game project from a GDD into out_dir.

    Every module is generated and validated in memory first; only when the
    whole project passes the placeholder + syntax guards is anything written
    to disk. Returns the list of written file paths.

    Raises AgentNotConfiguredError without AGENT_API_KEY, and
    CodeRejectedError when any generated file trips a guard.
    """
    gdd_dict = _gdd_to_dict(gdd)
    title = str(gdd_dict.get("title", "")).strip()
    if not title:
        raise CodeRejectedError("GDD has no title; refusing to generate a game from it")

    engine = _detect_engine(gdd_dict)
    if engine != "pygame":
        raise AgentNotConfiguredError(
            f"GDD names engine '{engine}', but this developer agent currently "
            "generates Pygame projects only. Refusing to pretend otherwise; "
            "extend PYGAME_MODULE_PLAN support before requesting that engine."
        )

    model = os.environ.get("AGENT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    client = _get_openai_client()
    logger.info("Generating Pygame project '%s' with model %s", title, model)

    generated: dict[str, str] = {}
    for filename, role in PYGAME_MODULE_PLAN:
        code_text = _request_module_code(
            client, model, gdd_dict, filename, role, list(generated.keys())
        )
        _validate_module(filename, code_text)
        generated[filename] = code_text
        logger.info("Module %s generated and validated (%d bytes)", filename, len(code_text))

    out_path = Path(out_dir)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for filename, code_text in generated.items():
            target = out_path / filename
            target.write_text(code_text, encoding="utf-8")
            written.append(target)
    except OSError as exc:
        raise CodeRejectedError(
            f"Could not write generated project to {out_path}: {exc}"
        ) from exc

    logger.info("Project written: %d files in %s", len(written), out_path)
    return written


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        description="Generate a complete game project from a GDD JSON file."
    )
    parser.add_argument("--gdd", required=True, help="Path to the GDD JSON file")
    parser.add_argument("--out", required=True, help="Output directory for the game project")
    args = parser.parse_args(argv)

    try:
        with open(args.gdd, "r", encoding="utf-8") as handle:
            gdd_data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not load GDD file %s: %s", args.gdd, exc)
        return 2

    try:
        written = generate_game(gdd_data, args.out)
    except (AgentNotConfiguredError, CodeRejectedError, TypeError) as exc:
        logger.error("Developer stage failed: %s", exc)
        return 1

    for path in written:
        print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
