from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CLAUDE_DIR_NAME = ".claude"
CCENV_DIR_NAME = ".ccenv"
SECRETS_FILE_NAME = ".env"
STATE_FILE_NAME = "state.json"
PROFILES_DIR_NAME = "profiles"
AGENTS_DIR_NAME = "agents"

MANAGED_FILES = ("CLAUDE.md", "mcp.json")
MANAGED_DIRS = ("skills",)

SECRET_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class Config:
    home: Path

    @property
    def claude_dir(self) -> Path:
        return self.home / CLAUDE_DIR_NAME

    @property
    def ccenv_dir(self) -> Path:
        return self.home / CCENV_DIR_NAME

    @property
    def profiles_dir(self) -> Path:
        return self.ccenv_dir / PROFILES_DIR_NAME

    @property
    def agents_dir(self) -> Path:
        return self.ccenv_dir / AGENTS_DIR_NAME

    @property
    def secrets_file(self) -> Path:
        return self.ccenv_dir / SECRETS_FILE_NAME

    @property
    def state_file(self) -> Path:
        return self.ccenv_dir / STATE_FILE_NAME

    @property
    def brief_file(self) -> Path:
        return self.ccenv_dir / "Brief.md"

    def agent_memory_dir(self, name: str) -> Path:
        return self.agents_dir / name / "Memory_Logs"


class CcenvError(Exception):
    """Top-level error raised by ccenv commands."""
