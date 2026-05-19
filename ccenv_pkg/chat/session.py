"""ChatSession and its profile/prompt helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..config import Config, CcenvError
from ..memory import append_session, ensure_agent_memory
from ..profiles import (
    load_manifest,
    resolve_model,
    resolve_output_dir,
    resolve_profile,
    resolve_profile_paths,
)
from ..storage import load_env_secrets, read_state
from ..tools import TOOL_DEFINITIONS, ToolExecutor
from .display import _blocks_to_dicts, _tool_status_detail, _tool_status_label
from .spinner import Spinner

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def load_active_profile_config(cfg: Config) -> tuple[str, Path, dict[str, Any], Path]:
    """Return (agent_name, profile_dir, manifest, instructions_path) for the active profile.

    Raises:
        CcenvError: If no profile is active or the profile directory is missing.
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
    """Combine profile instructions and agent memory into a system prompt."""
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


class ChatSession:
    """Manages a single interactive chat session with streaming and tool-use support."""

    def __init__(self, cfg: Config) -> None:
        if not ANTHROPIC_AVAILABLE:
            raise CcenvError(
                "anthropic library not installed. Run: pip install -r requirements.txt"
            )

        self.cfg = cfg

        self.agent_name, self.profile_dir, self.manifest, self.instructions_path = (
            load_active_profile_config(cfg)
        )
        self.instructions = self.instructions_path.read_text(encoding="utf-8")

        self.mem_dir = cfg.agent_memory_dir(self.agent_name)
        ensure_agent_memory(cfg, self.agent_name)
        context_file = self.mem_dir / "Context.md"
        self.context_text = (
            context_file.read_text(encoding="utf-8")
            if context_file.is_file()
            else "[No context yet]"
        )

        secrets = load_env_secrets(cfg.secrets_file)
        api_key = secrets.get("CLAUDE_API_KEY")
        if not api_key:
            raise CcenvError("CLAUDE_API_KEY not found in ~/.ccenv/.env")

        self.model = resolve_model(self.manifest)
        self.output_dir = resolve_output_dir(cfg, self.agent_name, self.manifest)
        self.output_dir.mkdir(parents=True, exist_ok=True)

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

    def _validate_history(self) -> None:
        """Inject synthetic tool_results for any dangling tool_use blocks at history end.

        Called before every API call. If the last message is an assistant message
        containing tool_use blocks (no following user message with tool_results),
        the API will return a 400. We inject synthetic results so the conversation
        can continue safely rather than crashing.

        Choice: inject (not truncate) — less destructive and lets Claude acknowledge
        the lost results before continuing.
        """
        if not self.conversation_history:
            return
        last = self.conversation_history[-1]
        if last["role"] != "assistant":
            return
        content = last.get("content", [])
        if not isinstance(content, list):
            return
        dangling = [
            b["id"] for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use" and "id" in b
        ]
        if not dangling:
            return
        print(
            f"⚠ History: {len(dangling)} dangling tool_use block(s); injecting synthetic tool_results",
            file=sys.stderr,
        )
        self.conversation_history.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tid,
                    "content": json.dumps({
                        "status": "lost",
                        "message": "Tool result was not recorded; ignore this call",
                    }),
                }
                for tid in dangling
            ],
        })

    def run_interactive_loop(self) -> None:
        """Stream responses token-by-token, animate tool calls, cap at 10 rounds/turn.

        Invariant enforced: every tool_use block in an assistant message has a
        matching tool_result block in the immediately following user message.
        """
        _tty = sys.stdout.isatty()

        while True:
            try:
                user_input = input(f"{self.agent_name}> ").strip()
            except EOFError:
                break

            if user_input.lower() in ("exit", "quit", "bye"):
                break
            if user_input == "/reset":
                self.conversation_history.clear()
                print("History reset.")
                continue
            if not user_input:
                continue

            # Snapshot index so we can roll back the entire turn on API error.
            # (A simple pop() would remove the tool_results message on iter 2+,
            # leaving an orphaned assistant tool_use block → 400 on the next call.)
            _turn_start = len(self.conversation_history)
            self.conversation_history.append({"role": "user", "content": user_input})

            for _ in range(10):  # hard cap: 10 tool-use rounds per user turn

                # Safety net: repair any dangling tool_use before hitting the API.
                self._validate_history()

                # ── API call (streaming) ────────────────────────────────────
                spinner = Spinner()
                spinner.start("Thinking…")
                first_token = False
                response = None

                try:
                    with self.client.messages.stream(
                        model=self.model,
                        max_tokens=8192,
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

                        spinner.stop()
                        if first_token:
                            sys.stdout.write("\n\n")
                            sys.stdout.flush()

                        response = stream.get_final_message()

                except Exception as exc:
                    spinner.stop()
                    print(f"\n✗ Error calling Claude API: {exc}", file=sys.stderr)
                    # Roll back the entire turn (user msg + any partial tool state),
                    # not just a single pop() which would leave orphaned tool_use blocks.
                    del self.conversation_history[_turn_start:]
                    break

                # Append the COMPLETE assistant message before doing anything else.
                self.conversation_history.append({
                    "role": "assistant",
                    "content": _blocks_to_dicts(response.content),
                })

                if response.stop_reason != "tool_use":
                    break

                # ── Tool execution ──────────────────────────────────────────
                # Collect ALL tool_use blocks first so we never miss one.
                tool_use_blocks = [
                    block for block in response.content
                    if hasattr(block, "type") and block.type == "tool_use"
                ]

                tool_results = []
                for block in tool_use_blocks:
                    label = _tool_status_label(block.name, block.input)
                    interactive = block.name == "run_command"

                    try:
                        if interactive or not _tty:
                            print(f"⏺ {label}…")
                            result = self.executor.execute(block.name, block.input)
                            detail = _tool_status_detail(block.name, result)
                            print(f"⏺ {label} {detail}")
                        else:
                            tool_spinner = Spinner()
                            tool_spinner.start(label)
                            result = self.executor.execute(block.name, block.input)
                            tool_spinner.stop()
                            detail = _tool_status_detail(block.name, result)
                            sys.stdout.write(f"⏺ {label} {detail}\n")
                            sys.stdout.flush()
                    except Exception as exc:
                        result = {"status": "error", "message": f"Tool execution interrupted: {exc}"}
                        print(f"⏺ {label} ✗ {exc}")

                    if result.get("status") == "switch_agent":
                        self._pending_switch = result["name"]

                    # Invariant: always append, even on error or rejection.
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

                # ONE user message with ALL tool_results, appended unconditionally.
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })

                if self._pending_switch:
                    break

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
        """Run a standalone session without switch-agent support.

        For full lifecycle management (agent switching, recursive apply),
        use CcenvManager._run_session() instead.
        """
        try:
            self.display_header()
            self.run_interactive_loop()
            self.log_session()
            return 0
        except CcenvError as exc:
            print(f"ccenv: error: {exc}", file=sys.stderr)
            return 1
