"""ccenvManager — Consolidated operations for chat, profile loading, and state management."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

from .config import Config, CcenvError
from .memory import append_session, ensure_agent_memory
from .profiles import (
    load_manifest,
    resolve_model,
    resolve_output_dir,
    resolve_profile,
    resolve_profile_paths,
)
from .storage import load_env_secrets, read_state
from .tools import TOOL_DEFINITIONS, ToolExecutor

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Terminal spinner (Braille, ~80 ms/frame, ANSI-guarded)
# ---------------------------------------------------------------------------

class Spinner:
    """Animated TTY spinner. All public methods are no-ops when stdout is not a TTY."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    _INTERVAL = 0.08  # seconds per frame

    def __init__(self) -> None:
        self._label = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tty = sys.stdout.isatty()

    def start(self, label: str = "") -> None:
        if not self._tty:
            return
        self._label = label
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._tty:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def _run(self) -> None:
        frames = self.FRAMES
        n = len(frames)
        i = 0
        while not self._stop.is_set():
            sys.stdout.write(f"\r{frames[i % n]} {self._label}")
            sys.stdout.flush()
            self._stop.wait(self._INTERVAL)
            i += 1


# ---------------------------------------------------------------------------
# Tool status display helpers
# ---------------------------------------------------------------------------

def _tool_status_label(name: str, inp: dict) -> str:
    """Human-readable label for a tool call (no leading ⏺)."""
    p = inp.get("path", "")
    return {
        "write_file":   f"Writing file: {p}",
        "read_file":    f"Reading file: {p}",
        "list_files":   f"Listing: {p or '.'}",
        "run_command":  f"Running: {inp.get('command', '')}",
        "open_file":    f"Opening: {p}",
        "switch_agent": f"Switching to: {inp.get('name', '')}",
    }.get(name, name)


def _tool_status_detail(name: str, result: dict) -> str:
    """✓/✗ outcome summary for a completed tool call."""
    s = result.get("status", "")
    if s == "rejected_by_user":
        return "✗ rejected"
    if s == "error":
        return f"✗ {result.get('message', 'error')}"
    # success variants
    if name == "write_file":
        b = result.get("bytes_written", 0)
        return f"✓ {b / 1024:.1f} KB" if b >= 100 else f"✓ {b} B"
    if name == "read_file":
        lines = len(result.get("content", "").splitlines())
        return f"✓ {lines} lines"
    if name == "list_files":
        n = len(result.get("entries", []))
        t = "+" if result.get("truncated") else ""
        return f"✓ {n}{t} entries"
    if name == "run_command":
        rc = result.get("return_code", 0)
        return f"✓ exit {rc}" if rc == 0 else f"✗ exit {rc}"
    if name == "open_file":
        return "✓ opened"
    if name == "switch_agent":
        return "✓ switching"
    return "✓"


# ---------------------------------------------------------------------------
# Profile / prompt helpers
# ---------------------------------------------------------------------------

def load_active_profile_config(cfg: Config) -> tuple[str, Path, dict[str, Any], Path]:
    """Load active profile configuration.

    Returns:
        Tuple of (agent_name, profile_dir, manifest, instructions_path)

    Raises:
        CcenvError: If no profile is active or profile not found.
    """
    state = read_state(cfg.state_file)
    agent_name = state.get("active_profile")

    if agent_name is None:
        raise CcenvError("No profile is active. Run: ccenv apply <profile>")

    profile_dir = resolve_profile(cfg, agent_name)
    manifest = load_manifest(profile_dir)
    instructions_path, _, _ = resolve_profile_paths(profile_dir, manifest)

    return agent_name, profile_dir, manifest, instructions_path


def build_system_prompt(instructions: str, context_text: str) -> str:
    """Build the system prompt by combining profile instructions and agent memory."""
    return f"""{instructions}

---

## Your Memory (Persistent Across Sessions)

{context_text}

---

## Instructions for This Session
- You are this agent. Embody their expertise and personality.
- Reference your memory when relevant.
- Log important lessons back via "ccenv memory log <agent>"
- When done, type 'exit' or 'quit' to end the chat.
"""


def _blocks_to_dicts(content: list) -> list[dict]:
    """Convert SDK content block objects to plain dicts for the conversation history."""
    result = []
    for block in content:
        if not hasattr(block, "type"):
            continue
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return result


# ---------------------------------------------------------------------------
# Chat session
# ---------------------------------------------------------------------------

class ChatSession:
    """Manages a single interactive chat session with streaming and tool-use support."""

    def __init__(self, cfg: Config) -> None:
        if not ANTHROPIC_AVAILABLE:
            raise CcenvError(
                "anthropic library not installed. Run: pip install -r requirements.txt"
            )

        self.cfg = cfg

        # Load active profile
        self.agent_name, self.profile_dir, self.manifest, self.instructions_path = (
            load_active_profile_config(cfg)
        )
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

        # Resolve model and output directory
        self.model = resolve_model(self.manifest)
        self.output_dir = resolve_output_dir(cfg, self.agent_name, self.manifest)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Anthropic client, tool executor, and conversation state
        self.client = Anthropic(api_key=api_key)
        self.executor = ToolExecutor(cfg, self.output_dir)
        self.system_prompt = build_system_prompt(self.instructions, self.context_text)
        self.conversation_history: list[dict[str, Any]] = []
        self._pending_switch: str | None = None

    def display_header(self) -> None:
        print(f"\n{'=' * 70}")
        print(f"Agent:  {self.agent_name.upper()}")
        print(f"Model:  {self.model}")
        print(f"Output: {self.output_dir}")
        print(f"Memory: {self.mem_dir}")
        print("Claude API: Connected ✓")
        print(f"{'=' * 70}\n")
        print("Chat Mode (type 'exit' or 'quit' to end session)\n")

    def run_interactive_loop(self) -> None:
        """Stream responses token-by-token, animate tool calls, cap at 10 rounds/turn."""
        _tty = sys.stdout.isatty()

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

            for _ in range(10):  # hard cap: 10 tool-use rounds per user turn
                # ── API call (streaming) ────────────────────────────────────────
                spinner = Spinner()
                spinner.start("Thinking…")
                first_token = False
                response = None

                try:
                    with self.client.messages.stream(
                        model=self.model,
                        max_tokens=8192,
                        # System prompt cached: stable for the full session
                        system=[{
                            "type": "text",
                            "text": self.system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }],
                        tools=TOOL_DEFINITIONS,
                        messages=self.conversation_history,
                    ) as stream:
                        for chunk in stream.text_stream:
                            if not first_token:
                                spinner.stop()
                                sys.stdout.write("\n")
                                sys.stdout.flush()
                                first_token = True
                            sys.stdout.write(chunk)
                            sys.stdout.flush()

                        spinner.stop()  # no-op if already stopped by first token
                        if first_token:
                            sys.stdout.write("\n\n")
                            sys.stdout.flush()

                        response = stream.get_final_message()

                except Exception as exc:
                    spinner.stop()
                    print(f"\n✗ Error calling Claude API: {exc}", file=sys.stderr)
                    self.conversation_history.pop()
                    break

                # Append full assistant message to history (tool_use blocks included)
                self.conversation_history.append({
                    "role": "assistant",
                    "content": _blocks_to_dicts(response.content),
                })

                if response.stop_reason != "tool_use":
                    break  # end_turn or other terminal reason → done with this user turn

                # ── Tool execution ──────────────────────────────────────────────
                tool_results = []
                for block in response.content:
                    if not hasattr(block, "type") or block.type != "tool_use":
                        continue

                    label = _tool_status_label(block.name, block.input)
                    interactive = block.name == "run_command"

                    if interactive or not _tty:
                        # Print status line with newline (interactive tool or non-TTY)
                        print(f"⏺ {label}…")
                        result = self.executor.execute(block.name, block.input)
                        detail = _tool_status_detail(block.name, result)
                        print(f"⏺ {label} {detail}")
                    else:
                        # Non-interactive TTY: spinner during execution, then result line
                        tool_spinner = Spinner()
                        tool_spinner.start(label)
                        result = self.executor.execute(block.name, block.input)
                        tool_spinner.stop()
                        detail = _tool_status_detail(block.name, result)
                        sys.stdout.write(f"⏺ {label} {detail}\n")
                        sys.stdout.flush()

                    if result.get("status") == "switch_agent":
                        self._pending_switch = result["name"]

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })

                if self._pending_switch:
                    break  # switch requested — stop tool loop

            # Break outer user-input loop if a switch was triggered
            if self._pending_switch:
                break

    def log_session(self) -> None:
        if not self.conversation_history:
            return

        session_content = "## Conversation\n\n"
        for msg in self.conversation_history:
            role = msg["role"].capitalize()
            content = msg["content"]
            if isinstance(content, str):
                session_content += f"\n**{role}:**\n{content}\n"
            elif isinstance(content, list):
                texts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
                ]
                if texts:
                    session_content += f"\n**{role}:**\n{chr(10).join(texts)}\n"

        append_session(self.mem_dir, self.agent_name, session_content)
        print(f"\n✓ Session logged to {self.mem_dir}/Sessions/")

    def run(self) -> int:
        try:
            self.display_header()
            self.run_interactive_loop()
            self.log_session()

            if self._pending_switch:
                from .commands import cmd_apply  # lazy import avoids circular dependency
                return cmd_apply(self.cfg, self._pending_switch, chat=True)

            return 0
        except CcenvError as exc:
            print(f"ccenv: error: {exc}", file=sys.stderr)
            return 1
