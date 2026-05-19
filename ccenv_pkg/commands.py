from __future__ import annotations

import json
import os
from pathlib import Path

from .config import Config
from .ccenvManager import CcenvManager
from .storage import read_state, write_state


def cmd_init(cfg: Config) -> int:
    cfg.ccenv_dir.mkdir(parents=True, exist_ok=True)
    cfg.profiles_dir.mkdir(parents=True, exist_ok=True)

    ccenv_env = cfg.ccenv_dir / ".env"
    if not ccenv_env.exists():
        ccenv_env.write_text(
            "# Local secrets for ccenv — DO NOT commit this file.\n"
            "# Profile mcp.json templates reference these by name, e.g. {{ MY_TOKEN }}.\n"
            "CLAUDE_API_KEY=sk_xxxxxxxxxxxxxxxxxxxx\n"
            "GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx\n"
            "JENKINS_TOKEN=jnkns_xxxxxxxxxxxxxxxxx\n"
            "FIGMA_API_KEY=figd_xxxxxxxxxxxxxxxxxxx\n",
            encoding="utf-8",
        )
        try:
            os.chmod(ccenv_env, 0o600)
        except OSError:
            pass

    if not cfg.state_file.exists():
        write_state(cfg.state_file, None)

    cfg.agents_dir.mkdir(parents=True, exist_ok=True)

    if not cfg.brief_file.exists():
        cfg.brief_file.write_text(
            "# Brief — ccenv Project Dashboard\n\n"
            "| Date | Agent | Activity |\n"
            "| ---- | ----- | -------- |\n",
            encoding="utf-8",
        )

    example = cfg.profiles_dir / "example"
    if not example.exists():
        (example / "skills" / "hello-skill").mkdir(parents=True)
        (example / "profile.yaml").write_text(
            "name: example\n"
            "description: Minimal example profile created by `ccenv init`.\n"
            "instructions: CLAUDE.md\n"
            "mcp_template: mcp.json\n"
            "skills:\n"
            "  - skills/hello-skill\n",
            encoding="utf-8",
        )
        (example / "CLAUDE.md").write_text(
            "# Example profile\n\nThis is the example profile. Replace it.\n",
            encoding="utf-8",
        )
        (example / "mcp.json").write_text(
            json.dumps({"mcpServers": {}}, indent=2) + "\n",
            encoding="utf-8",
        )
        (example / "skills" / "hello-skill" / "SKILL.md").write_text(
            "---\nname: hello-skill\ndescription: Placeholder skill.\n---\n\n"
            "# hello-skill\n\nReplace me.\n",
            encoding="utf-8",
        )

    print(f"Initialized ccenv at {cfg.ccenv_dir}")
    print(f"  profiles dir:  {cfg.profiles_dir}")
    print(f"  secrets file:  {cfg.secrets_file}")
    print(f"  state file:    {cfg.state_file}")
    print("Try:  ccenv apply example")
    return 0


def cmd_apply(cfg: Config, name: str, chat: bool = True) -> int:
    return CcenvManager(cfg).apply(name, chat=chat)


def cmd_switch(cfg: Config, name: str, chat: bool = True) -> int:
    state = read_state(cfg.state_file)
    current = state.get("active_profile")
    if current == name:
        print(f"Profile '{name}' is already active. Re-applying.")
    else:
        print(f"Switching from '{current or '<none>'}' to '{name}'.")
    return CcenvManager(cfg).apply(name, chat=chat)


def cmd_status(cfg: Config) -> int:
    state = read_state(cfg.state_file)
    active = state.get("active_profile")
    if active is None:
        print("No profile is active. Run `ccenv apply <profile>`.")
    else:
        print(f"Active profile: {active}")

    if cfg.profiles_dir.is_dir():
        names = sorted(p.name for p in cfg.profiles_dir.iterdir() if p.is_dir())
        if names:
            print("Available profiles: " + ", ".join(names))
    return 0
