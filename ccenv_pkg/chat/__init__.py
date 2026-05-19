"""Public API for the chat sub-package."""

from __future__ import annotations

from .display import _blocks_to_dicts, _tool_status_detail, _tool_status_label
from .session import ChatSession, build_system_prompt, load_active_profile_config
from .spinner import Spinner


def cmd_chat(cfg) -> int:
    """Start an interactive chat session with the active agent."""
    from ..ccenvManager import CcenvManager
    return CcenvManager(cfg).start()
