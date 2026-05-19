"""ccenvManager — Consolidated operations for chat, profile loading, and state management."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .config import Config, CcenvError
from .memory import append_session, ensure_agent_memory
from .profiles import load_manifest, resolve_profile, resolve_profile_paths
from .storage import load_env_secrets, read_state

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def load_active_profile_config(cfg: Config) -> tuple[str, Path, dict[str, Any], Path]:
    """Load active profile configuration without duplicating profile resolution.
    
    Returns:
        Tuple of (agent_name, profile_dir, manifest, instructions_path)
    
    Raises:
        CcenvError: If no profile is active or profile not found.
    """
    state = read_state(cfg.state_file)
    agent_name = state.get("active_profile")
    
    if agent_name is None:
        raise CcenvError("No profile is active. Run: main apply <profile>")
    
    profile_dir = resolve_profile(cfg, agent_name)
    manifest = load_manifest(profile_dir)
    instructions_path, _, _ = resolve_profile_paths(profile_dir, manifest)
    
    return agent_name, profile_dir, manifest, instructions_path


def build_system_prompt(instructions: str, context_text: str) -> str:
    """Build the system prompt for Claude by combining instructions and memory context."""
    return f"""{instructions}

---

## Your Memory (Persistent Across Sessions)

{context_text}

---

## Instructions for This Session
- You are this agent. Embody their expertise and personality.
- Reference your memory when relevant.
- Log important lessons back via "main memory log <agent>"
- When done, type 'exit' or 'quit' to end the chat.
"""


class ChatSession:
    """Encapsulates all chat session initialization and management."""
    
    def __init__(self, cfg: Config):
        """Initialize a chat session with the active profile.
        
        Args:
            cfg: Config object with home directory and paths.
        
        Raises:
            CcenvError: If anthropic is not installed, no profile is active,
                       or CLAUDE_API_KEY is missing.
        """
        if not ANTHROPIC_AVAILABLE:
            raise CcenvError(
                "anthropic library not installed. Run: pip install -r requirements.txt"
            )
        
        # Load active profile configuration
        self.agent_name, self.profile_dir, self.manifest, self.instructions_path = (
            load_active_profile_config(cfg)
        )
        
        # Read instructions
        self.instructions = self.instructions_path.read_text(encoding="utf-8")
        
        # Load agent memory
        self.mem_dir = cfg.agent_memory_dir(self.agent_name)
        ensure_agent_memory(cfg, self.agent_name)
        context_file = self.mem_dir / "Context.md"
        self.context_text = (
            context_file.read_text(encoding="utf-8")
            if context_file.is_file()
            else "[No context yet]"
        )
        
        # Load API key
        secrets = load_env_secrets(cfg.secrets_file)
        api_key = secrets.get("CLAUDE_API_KEY")
        if not api_key:
            raise CcenvError("CLAUDE_API_KEY not found in ~/.ccenv/.env")
        
        # Initialize client and conversation
        self.client = Anthropic(api_key=api_key)
        self.system_prompt = build_system_prompt(self.instructions, self.context_text)
        self.conversation_history: list[dict[str, Any]] = []
    
    def display_header(self) -> None:
        """Display the chat session header."""
        print(f"\n{'='*70}")
        print(f"Agent: {self.agent_name.upper()}")
        print("Claude API: Connected ✓")
        print(f"Memory: {self.mem_dir}")
        print(f"{'='*70}\n")
        print("Chat Mode (type 'exit' or 'quit' to end session)\n")
    
    def run_interactive_loop(self) -> None:
        """Run the interactive chat loop until user exits."""
        while True:
            try:
                user_input = input(f"{self.agent_name}> ").strip()
            except EOFError:
                break
            
            if user_input.lower() in ("exit", "quit", "bye"):
                break
            if not user_input:
                continue
            
            self.conversation_history.append({"role": "user", "content": user_input})
            
            try:
                response = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=2048,
                    system=self.system_prompt,
                    messages=self.conversation_history,
                )
                assistant_message = response.content[0].text
                self.conversation_history.append(
                    {"role": "assistant", "content": assistant_message}
                )
                print(f"\n{assistant_message}\n")
            except Exception as exc:
                print(f"\n✗ Error calling Claude API: {exc}\n", file=sys.stderr)
                self.conversation_history.pop()
    
    def log_session(self) -> None:
        """Log the conversation history to the agent's memory."""
        if not self.conversation_history:
            return
        
        session_content = "## Conversation\n\n"
        for msg in self.conversation_history:
            role = msg["role"].capitalize()
            session_content += f"\n**{role}:**\n{msg['content']}\n"
        
        append_session(self.mem_dir, self.agent_name, session_content)
        print(f"\n✓ Session logged to {self.mem_dir}/Sessions/")
    
    def run(self) -> int:
        """Run the complete chat session: display header, loop, log.
        
        Returns:
            Exit code (0 on success).
        """
        try:
            self.display_header()
            self.run_interactive_loop()
            self.log_session()
            return 0
        except CcenvError as exc:
            print(f"ccenv: error: {exc}", file=sys.stderr)
            return 1
