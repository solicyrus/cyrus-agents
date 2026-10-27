"""Game Designer Agent — the Visionary Director, as code.

Takes a raw game idea and produces a validated Game Design Document (GDD).
The analysis is done by an LLM (OpenAI chat completions, strict JSON), and the
result is checked by a deterministic completeness validator. If the LLM output
is missing required sections, this agent raises a loud error listing the gaps —
it never invents the missing design work itself.

Honesty contract (studio red line):
  * No AGENT_API_KEY in the environment -> AgentNotConfiguredError, no fake GDD.
  * Incomplete or unparseable LLM output -> GDDValidationError listing gaps.

Environment:
  AGENT_API_KEY  OpenAI API key (required for analyze_idea).
  AGENT_MODEL    Model name (default "gpt-4o").
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("game_designer_agent")

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

# Retry policy for OpenAI calls (same as the game wing's strength pass):
# max 3 attempts, backoff ~2s then ~5s; only transient failures are retried
# (rate limits, connection/timeout errors, 429/5xx API responses).
RETRY_DELAYS = (2, 5)
DEFAULT_MODEL = "gpt-4o"


class AgentNotConfiguredError(RuntimeError):
    """Raised when the agent cannot run because its environment is incomplete."""


class GDDValidationError(RuntimeError):
    """Raised when a GDD (from the LLM or from disk) is incomplete."""


@dataclass
class GDD:
    """Game Design Document schema for the studio."""

    title: str = ""
    pitch: str = ""
    genre: str = ""
    platform: str = ""
    core_loop: str = ""
    mechanics: list[str] = field(default_factory=list)
    scoring_system: str = ""
    physics_rules: str = ""
    controls: str = ""
    win_conditions: str = ""
    lose_conditions: str = ""
    levels: list[str] = field(default_factory=list)
    art_sound_direction: str = ""


# (field name, kind) for every section a complete GDD must carry.
REQUIRED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("title", "text"),
    ("pitch", "text"),
    ("genre", "text"),
    ("platform", "text"),
    ("core_loop", "text"),
    ("mechanics", "list"),
    ("scoring_system", "text"),
    ("physics_rules", "text"),
    ("controls", "text"),
    ("win_conditions", "text"),
    ("lose_conditions", "text"),
    ("levels", "list"),
    ("art_sound_direction", "text"),
)


def validate_gdd(gdd: GDD) -> list[str]:
    """Deterministically check a GDD for missing or empty required sections.

    Returns a list of human-readable gap descriptions; an empty list means the
    GDD is complete. This function makes no LLM calls and invents nothing.
    """
    gaps: list[str] = []
    for name, kind in REQUIRED_SECTIONS:
        value = getattr(gdd, name, None)
        if kind == "text":
            if not isinstance(value, str) or not value.strip():
                gaps.append(f"section '{name}' is missing or empty")
        elif kind == "list":
            if not isinstance(value, list) or not value:
                gaps.append(f"section '{name}' is missing or an empty list")
            elif not any(isinstance(item, str) and item.strip() for item in value):
                gaps.append(f"section '{name}' contains no usable entries")
    return gaps


def gdd_from_dict(data: dict[str, Any]) -> GDD:
    """Build a GDD from parsed JSON, tolerating missing keys (validation
    downstream will report them as gaps instead of crashing here)."""
    if not isinstance(data, dict):
        raise GDDValidationError(
            f"GDD payload must be a JSON object, got {type(data).__name__}"
        )

    def text(key: str) -> str:
        value = data.get(key, "")
        if isinstance(value, list):
            return "; ".join(str(item) for item in value)
        return str(value) if value is not None else ""

    def str_list(key: str) -> list[str]:
        value = data.get(key, [])
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    return GDD(
        title=text("title"),
        pitch=text("pitch"),
        genre=text("genre"),
        platform=text("platform"),
        core_loop=text("core_loop"),
        mechanics=str_list("mechanics"),
        scoring_system=text("scoring_system"),
        physics_rules=text("physics_rules"),
        controls=text("controls"),
        win_conditions=text("win_conditions"),
        lose_conditions=text("lose_conditions"),
        levels=str_list("levels"),
        art_sound_direction=text("art_sound_direction"),
    )


def _get_openai_client():
    """Create an OpenAI client from the environment, failing loudly and
    specifically when the key or the package is missing."""
    api_key = os.environ.get("AGENT_API_KEY", "").strip()
    if not api_key:
        raise AgentNotConfiguredError(
            "AGENT_API_KEY not configured: set the AGENT_API_KEY environment "
            "variable (or GitHub secret) before running the designer agent. "
            "Refusing to fabricate a GDD without the LLM."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AgentNotConfiguredError(
            "The 'openai' Python package is not installed in this environment; "
            "install the game wing requirements before running the designer agent."
        ) from exc
    return OpenAI(api_key=api_key)


def _create_with_retry(client, **kwargs):
    """client.chat.completions.create with retry + exponential backoff.

    Retries only transient failures (rate limit, connection, timeout, and
    API errors with status 429 or >= 500). Non-transient errors raise at once.
    """
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


def _build_design_prompt(idea_text: str) -> list[dict[str, str]]:
    schema_keys = [name for name, _kind in REQUIRED_SECTIONS]
    system = (
        "You are the Visionary Director of a game studio: a senior game designer. "
        "Analyse the raw game idea and produce a complete Game Design Document. "
        "Reply with STRICT JSON ONLY — no markdown fences, no commentary. "
        "The JSON object must contain exactly these keys: "
        + ", ".join(schema_keys)
        + ". 'mechanics' and 'levels' must be JSON arrays of strings; every other "
        "value must be a non-empty string with concrete, implementable detail. "
        "Design a scoring system, explicit physics rules, controls, win and lose "
        "conditions, and a level/progression outline. Be specific enough that a "
        "programmer can implement the game without asking follow-up questions."
    )
    user = f"Raw game idea:\n{idea_text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse the LLM reply as JSON, tolerating accidental markdown fences but
    failing loudly on anything that is not a JSON object."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GDDValidationError(
            f"Designer LLM output was not valid JSON: {exc}. "
            f"First 200 chars received: {text[:200]!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise GDDValidationError(
            f"Designer LLM output was JSON but not an object: {type(parsed).__name__}"
        )
    return parsed


def analyze_idea(idea_text: str) -> GDD:
    """Analyse a raw game idea with the LLM and return a validated GDD.

    Raises:
        ValueError: the idea text is empty.
        AgentNotConfiguredError: AGENT_API_KEY (or the openai package) missing.
        GDDValidationError: the LLM output was unparseable or incomplete; the
            message lists every missing/empty required section.
    """
    if not idea_text or not idea_text.strip():
        raise ValueError("analyze_idea requires a non-empty idea text")

    model = os.environ.get("AGENT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    client = _get_openai_client()
    logger.info("Requesting GDD from model %s for idea of %d chars", model, len(idea_text))

    response = _create_with_retry(
        client,
        model=model,
        messages=_build_design_prompt(idea_text.strip()),
        temperature=0.4,
    )
    content = response.choices[0].message.content
    if not content:
        raise GDDValidationError("Designer LLM returned an empty response")

    gdd = gdd_from_dict(_parse_llm_json(content))
    gaps = validate_gdd(gdd)
    if gaps:
        raise GDDValidationError(
            "Designer LLM produced an incomplete GDD; refusing to invent the "
            "missing design. Gaps: " + "; ".join(gaps)
        )
    logger.info("GDD validated complete: '%s' (%s)", gdd.title, gdd.genre)
    return gdd


def load_gdd_file(path: str) -> GDD:
    """Load a GDD JSON file from disk and validate it (used by the pipeline
    and by humans re-checking a saved design)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise GDDValidationError(f"GDD file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GDDValidationError(f"GDD file is not valid JSON: {path}: {exc}") from exc
    gdd = gdd_from_dict(data)
    gaps = validate_gdd(gdd)
    if gaps:
        raise GDDValidationError(
            f"GDD file {path} is incomplete. Gaps: " + "; ".join(gaps)
        )
    return gdd


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        description="Analyse a raw game idea into a validated GDD (JSON on stdout)."
    )
    parser.add_argument("idea", nargs="?", help="The raw game idea text")
    parser.add_argument("--idea-file", help="Read the idea text from this file instead")
    parser.add_argument("--out", help="Also write the GDD JSON to this path")
    args = parser.parse_args(argv)

    idea_text = args.idea or ""
    if args.idea_file:
        try:
            with open(args.idea_file, "r", encoding="utf-8") as handle:
                idea_text = handle.read()
        except OSError as exc:
            logger.error("Could not read idea file %s: %s", args.idea_file, exc)
            return 2

    try:
        gdd = analyze_idea(idea_text)
    except (AgentNotConfiguredError, GDDValidationError, ValueError) as exc:
        logger.error("Designer stage failed: %s", exc)
        return 1

    payload = json.dumps(asdict(gdd), indent=2, ensure_ascii=False)
    print(payload)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(payload + "\n")
            logger.info("GDD written to %s", args.out)
        except OSError as exc:
            logger.error("Could not write GDD to %s: %s", args.out, exc)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
