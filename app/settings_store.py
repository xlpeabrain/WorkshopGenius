"""Persistent app settings (model selection)."""

import json
import shutil
from pathlib import Path

SETTINGS_PATH = Path("app_settings.json")

DEFAULTS: dict = {
    "claude_model": "claude-sonnet-4-6",
}


def load() -> dict:
    if SETTINGS_PATH.exists():
        try:
            stored = json.loads(SETTINGS_PATH.read_text())
            return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}
        except Exception:
            pass
    return DEFAULTS.copy()


def save(updates: dict) -> dict:
    current = load()
    current.update({k: v for k, v in updates.items() if k in DEFAULTS})
    SETTINGS_PATH.write_text(json.dumps(current, indent=2))
    return current


def is_configured() -> bool:
    """Return True if the claude CLI is available (checks PATH and common install dirs)."""
    from app.ai import _find_claude
    return _find_claude() is not None
