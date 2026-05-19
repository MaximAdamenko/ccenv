from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .config import CcenvError, DEFAULT_MODEL, SECRET_PATTERN

if TYPE_CHECKING:
    from .config import Config
from .storage import load_yaml


def render_template(template_text: str, secrets: dict[str, str]) -> str:
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in secrets:
            missing.append(name)
            return match.group(0)
        return secrets[name]

    rendered = SECRET_PATTERN.sub(replace, template_text)
    if missing:
        raise CcenvError(
            "Missing secrets in ~/.ccenv/.env: "
            + ", ".join(sorted(set(missing)))
            + "\nAdd them and re-run."
        )
    return rendered


def validate_json(text: str) -> None:
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        raise CcenvError(f"Rendered mcp.json is not valid JSON: {exc}") from exc


def resolve_profile(cfg: Config, name: str) -> Path:
    profile_dir = cfg.profiles_dir / name
    if not profile_dir.is_dir():
        raise CcenvError(
            f"Profile '{name}' not found at {profile_dir}.\n"
            "Run `ccenv init` first, or check the spelling."
        )
    return profile_dir


def load_manifest(profile_dir: Path) -> dict[str, Any]:
    return load_yaml(profile_dir / "profile.yaml")


def resolve_profile_paths(profile_dir: Path, manifest: dict[str, Any]) -> tuple[Path, Path, list[str]]:
    instructions_rel = manifest.get("instructions", "CLAUDE.md")
    mcp_rel = manifest.get("mcp_template", "mcp.json")
    skills = manifest.get("skills", []) or []

    if not isinstance(skills, list):
        raise CcenvError("`skills` in profile.yaml must be a list of paths")

    instructions_path = profile_dir / instructions_rel
    mcp_path = profile_dir / mcp_rel

    if not instructions_path.is_file():
        raise CcenvError(f"Instructions file not found: {instructions_path}")
    if not mcp_path.is_file():
        raise CcenvError(f"MCP template not found: {mcp_path}")

    return instructions_path, mcp_path, skills


def resolve_model(manifest: dict[str, Any]) -> str:
    return manifest.get("model") or DEFAULT_MODEL


def resolve_output_dir(cfg: "Config", agent_name: str, manifest: dict[str, Any]) -> Path:
    custom = manifest.get("output_dir")
    if custom:
        p = Path(custom).expanduser()
        if not p.is_absolute():
            p = cfg.home / p
        return p
    return cfg.ccenv_dir / "output" / agent_name


def render_mcp(mcp_path: Path, secrets: dict[str, str]) -> str:
    rendered = render_template(mcp_path.read_text(encoding="utf-8"), secrets)
    validate_json(rendered)
    return rendered
