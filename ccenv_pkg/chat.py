"""Chat command using the ChatSession manager."""

from __future__ import annotations

from .config import Config, CcenvError
from .ccenvManager import ChatSession


def cmd_chat(cfg: Config) -> int:
    """Start an interactive chat session with the active agent.
    
    Args:
        cfg: Config object with home directory and paths.
    
    Returns:
        Exit code (0 on success, 1 on error).
    """
    try:
        session = ChatSession(cfg)
        return session.run()
    except CcenvError as exc:
        import sys
        print(f"ccenv: error: {exc}", file=sys.stderr)
        return 1
