from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from .config import CcenvError


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CcenvError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise CcenvError(f"Expected a YAML mapping at {path}, got {type(data).__name__}")
    return data


def load_env_secrets(env_path: Path) -> dict[str, str]:
    if not env_path.is_file():
        return {}
    return {k: str(v) for k, v in dotenv_values(env_path).items() if v is not None}


def read_state(state_path: Path) -> dict[str, Any]:
    if not state_path.is_file():
        return {"active_profile": None}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CcenvError(f"State file is corrupt ({state_path}): {exc}") from exc


def write_state(state_path: Path, active: str | None) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"active_profile": active}, indent=2) + "\n",
        encoding="utf-8",
    )
