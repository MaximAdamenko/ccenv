from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from .config import CcenvError

MANAGED_FILES = ("CLAUDE.md", "mcp.json")
MANAGED_DIRS = ("skills",)


def wipe_managed_files(claude_dir: Path) -> None:
    if not claude_dir.exists():
        return
    if not claude_dir.is_dir():
        raise CcenvError(f"{claude_dir} exists but is not a directory")
    for name in MANAGED_FILES:
        target = claude_dir / name
        if target.is_symlink() or target.is_file():
            target.unlink()


def wipe_managed_dirs(claude_dir: Path) -> None:
    if not claude_dir.exists():
        return
    for name in MANAGED_DIRS:
        target = claude_dir / name
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)


def wipe_managed_targets(claude_dir: Path) -> None:
    wipe_managed_files(claude_dir)
    wipe_managed_dirs(claude_dir)


def copy_skills(profile_dir: Path, skill_rel_paths: list[str], dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for rel in skill_rel_paths:
        src = (profile_dir / rel).resolve()
        if not src.is_dir():
            raise CcenvError(f"Skill directory not found: {src}")
        shutil.copytree(src, dest / src.name)
        count += 1
    return count


def write_profile(
    claude_dir: Path,
    instructions_path: Path,
    mcp_rendered: str,
    profile_dir: Path,
    skills: list[str],
) -> int:
    claude_dir.mkdir(parents=True, exist_ok=True)
    wipe_managed_targets(claude_dir)
    shutil.copyfile(instructions_path, claude_dir / "CLAUDE.md")
    (claude_dir / "mcp.json").write_text(mcp_rendered, encoding="utf-8")
    return copy_skills(profile_dir, skills, claude_dir / "skills")
