"""CcenvManager — top-level orchestrator for the ccenv agent lifecycle.

Owns the full flow:
  1. deploy a profile (write files to ~/.claude/)
  2. open a ChatSession and drive it interactively
  3. handle agent switches requested from inside the session
  4. log the session when it ends

Both `commands.py` and `cmd_chat` delegate here instead of creating
ChatSessions directly. This removes the lazy circular import that used to
live inside ChatSession.run().

Component map
─────────────
  CcenvManager          ← you are here (orchestration)
  chat/session.py       ← ChatSession (single turn loop, streaming, tool use)
  chat/spinner.py       ← Spinner (Braille animation, TTY-guarded)
  chat/display.py       ← status labels, detail lines, block serialisation
  tools.py              ← ToolExecutor + TOOL_DEFINITIONS (6 tools)
  profiles.py           ← manifest loading, model/output-dir resolution
  deployment.py         ← write_profile (file diffing + symlink management)
  memory.py             ← agent memory init + session logging
  storage.py            ← load_env_secrets, read/write_state, load_yaml
  config.py             ← Config paths, CcenvError, constants
"""

from __future__ import annotations

import sys

from .chat import ChatSession
from .config import Config, CcenvError
from .deployment import write_profile
from .memory import ensure_agent_memory
from .profiles import load_manifest, render_mcp, resolve_profile, resolve_profile_paths
from .storage import load_env_secrets, write_state


class CcenvManager:
    """Lifecycle manager for ccenv chat sessions.

    Usage
    -----
    manager = CcenvManager(cfg)
    manager.start()              # chat with currently active profile
    manager.apply("devops")      # deploy + chat
    manager.apply("devops", chat=False)  # deploy only
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    # ── Public API ──────────────────────────────────────────────────────────

    def start(self) -> int:
        """Start a chat session with the currently active profile."""
        if not sys.stdin.isatty():
            print("Skipping interactive chat because stdin is not a TTY.")
            return 0
        try:
            session = ChatSession(self.cfg)
        except CcenvError as exc:
            print(f"ccenv: error: {exc}", file=sys.stderr)
            return 1
        return self._run_session(session)

    def apply(self, name: str, chat: bool = True) -> int:
        """Deploy profile *name* and optionally open a chat session.

        Prints the same summary lines as the old cmd_apply so the CLI output
        is unchanged.
        """
        try:
            self._deploy_profile(name)
        except CcenvError as exc:
            print(f"ccenv: error: {exc}", file=sys.stderr)
            return 1

        if chat:
            return self.start()
        return 0

    # ── Internal ────────────────────────────────────────────────────────────

    def _deploy_profile(self, name: str) -> None:
        """Write profile files into ~/.claude/ and update active-profile state."""
        profile_dir = resolve_profile(self.cfg, name)
        manifest = load_manifest(profile_dir)
        instructions_path, mcp_path, skills = resolve_profile_paths(profile_dir, manifest)

        secrets = load_env_secrets(self.cfg.secrets_file)
        mcp_rendered = render_mcp(mcp_path, secrets)

        skill_count = write_profile(
            self.cfg.claude_dir,
            instructions_path,
            mcp_rendered,
            profile_dir,
            skills,
        )
        write_state(self.cfg.state_file, name)
        ensure_agent_memory(self.cfg, name)

        print(f"Applied profile '{name}' to {self.cfg.claude_dir}")
        print(f"  CLAUDE.md  <- {instructions_path}")
        print(f"  mcp.json   <- {mcp_path} (rendered)")
        print(f"  skills/    <- {skill_count} skill(s)")
        print(f"  memory/    <- {self.cfg.agent_memory_dir(name)}")

    def _run_session(self, session: ChatSession) -> int:
        """Drive *session* to completion and handle any requested agent switch."""
        try:
            session.display_header()
            session.run_interactive_loop()
            session.log_session()
        except CcenvError as exc:
            print(f"ccenv: error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"✗ Unexpected error during session: {exc}", file=sys.stderr)
            return 1

        if session._pending_switch:
            return self.apply(session._pending_switch, chat=True)

        return 0
