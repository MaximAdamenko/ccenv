from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .config import Config
from .deployment import write_profile
from .memory import ensure_agent_memory
from .profiles import (
    load_manifest,
    render_mcp,
    resolve_profile,
    resolve_profile_paths,
)
from .storage import load_env_secrets, read_state, write_state
from .ccenvManager import ChatSession


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
    profile_dir = resolve_profile(cfg, name)
    manifest = load_manifest(profile_dir)
    instructions_path, mcp_path, skills = resolve_profile_paths(profile_dir, manifest)

    secrets = load_env_secrets(cfg.secrets_file)
    mcp_rendered = render_mcp(mcp_path, secrets)

    skill_count = write_profile(
        cfg.claude_dir,
        instructions_path,
        mcp_rendered,
        profile_dir,
        skills,
    )
    write_state(cfg.state_file, name)
    ensure_agent_memory(cfg, name)

    print(f"Applied profile '{name}' to {cfg.claude_dir}")
    print(f"  CLAUDE.md  <- {instructions_path}")
    print(f"  mcp.json   <- {mcp_path} (rendered)")
    print(f"  skills/    <- {skill_count} skill(s)")
    print(f"  memory/    <- {cfg.agent_memory_dir(name)}")

    if chat and sys.stdin.isatty():
        try:
            session = ChatSession(cfg)
            return session.run()
        except Exception as exc:
            print(f"Error starting chat: {exc}", file=sys.stderr)
            return 1
    if chat:
        print("Skipping interactive chat because stdin is not a TTY.")
    return 0


def cmd_switch(cfg: Config, name: str, chat: bool = True) -> int:
    state = read_state(cfg.state_file)
    current = state.get("active_profile")
    if current == name:
        print(f"Profile '{name}' is already active. Re-applying.")
    else:
        print(f"Switching from '{current or '<none>'}' to '{name}'.")
    return cmd_apply(cfg, name, chat=chat)


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
