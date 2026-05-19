"""Claude CLI integration for analyzing client challenges and selecting slides."""

import asyncio
import json
import os
import re
import shutil

from app.catalog import get_catalog_for_prompt
from app.config import settings as env_config

# Common installation paths for the claude CLI that may be missing when uvicorn
# is started via --reload (macOS spawns child processes with the system PATH).
_CLAUDE_SEARCH_PATHS = [
    os.path.expanduser("~/.local/bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
]


def _find_claude() -> str | None:
    """Locate the claude CLI, checking extra paths if shutil.which misses it."""
    found = shutil.which("claude")
    if found:
        return found
    for directory in _CLAUDE_SEARCH_PATHS:
        candidate = os.path.join(directory, "claude")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _subprocess_env() -> dict:
    """Return an environment dict that ensures claude's directory is on PATH.

    ANTHROPIC_API_KEY is stripped so the CLI uses its OAuth session rather than
    an ambient (possibly invalid) key from the parent shell environment.
    """
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    existing = env.get("PATH", "")
    extras = [p for p in _CLAUDE_SEARCH_PATHS if p not in existing]
    if extras:
        env["PATH"] = ":".join(extras) + ":" + existing
    return env

SYSTEM_PROMPT_PREFIX = """\
You are an expert Kong Solutions Engineer helping assemble workshop slide decks for client enablement sessions.

Your job:
1. Analyze the client's technical challenges
2. Select the most relevant slides from the library below
3. Return a structured JSON response — no prose before or after the JSON

SELECTION RULES:
- Always include the title slide (index 0) of any selected deck
- Select 5–15 slides per deck (not entire decks)
- For a 2-hour workshop, target 25–40 slides total; scale proportionally for other durations
- Sequence decks from foundational to advanced
- "Platform Architecture" deck should come first if included
- If the client mentions specific topics (auth, rate limiting, observability, etc.), select slides within the relevant deck that focus on those topics
- Only include a deck if it directly addresses a stated challenge

OUTPUT: Return ONLY valid JSON with this exact structure:
{
  "workshop_title": "string — concise title for this workshop",
  "estimated_duration_hours": number,
  "selections": [
    {
      "deck_id": "string — must match a deck id from the library",
      "slide_indices": [array of 0-based integers],
      "rationale": "one sentence explaining why this deck was selected"
    }
  ],
  "summary": "2–3 sentence summary of what this workshop covers and how it addresses the challenges"
}

SLIDE LIBRARY:
==============
"""

USER_MESSAGE_TEMPLATE = """\
CLIENT CHALLENGES:
==================
{challenge_text}

Analyze these challenges and select the most relevant slides from the library. \
Return only the JSON response."""


class UpstreamAPIError(Exception):
    """Raised when the claude CLI call fails."""


def _build_system_prompt(catalog: dict) -> str:
    return SYSTEM_PROMPT_PREFIX + get_catalog_for_prompt(catalog)


def _extract_json(text: str) -> dict:
    """Parse JSON from CLI response, stripping markdown fences if present."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence_match:
        text = fence_match.group(1)
    return json.loads(text)


async def analyze_challenges(
    challenge_text: str,
    catalog: dict,
    app_settings: dict,
) -> dict:
    cli_path = _find_claude()
    if not cli_path:
        raise UpstreamAPIError(
            "The 'claude' CLI was not found. "
            "Make sure Claude Code is installed and on your PATH."
        )

    model = app_settings.get("claude_model", env_config.model)
    system_prompt = _build_system_prompt(catalog)
    user_message = USER_MESSAGE_TEMPLATE.format(challenge_text=challenge_text)

    cmd = [
        cli_path, "-p", user_message,
        "--system-prompt", system_prompt,
        "--output-format", "json",
        "--model", model,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_subprocess_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        raise UpstreamAPIError(
            "Claude CLI timed out after 120 seconds. Try again."
        )
    except Exception as exc:
        raise UpstreamAPIError(f"Failed to run claude CLI: {exc}") from exc

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        out = stdout.decode(errors="replace").strip()
        combined = (err or out or "(no output)").strip()
        if "not logged in" in combined.lower() or "auth" in combined.lower():
            raise UpstreamAPIError(
                "Claude CLI is not authenticated. Run 'claude' in your terminal and log in first."
            )
        raise UpstreamAPIError(
            f"Claude CLI exited with code {proc.returncode}.\n"
            f"stderr: {err[:400] or '(empty)'}\n"
            f"stdout: {out[:400] or '(empty)'}"
        )

    raw_output = stdout.decode(errors="replace").strip()
    try:
        cli_json = json.loads(raw_output)
    except json.JSONDecodeError:
        raise UpstreamAPIError(f"Unexpected CLI output: {raw_output[:300]}")

    if cli_json.get("is_error"):
        raise UpstreamAPIError(f"Claude CLI error: {cli_json.get('result', '')[:300]}")

    result_text = cli_json.get("result", "")
    try:
        return _extract_json(result_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned non-JSON content: {result_text[:500]}") from e
