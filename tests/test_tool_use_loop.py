"""Tests for the tool-use loop invariant, history validator, and /reset command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Shared test helpers (mirrors test_streaming.py)
# ---------------------------------------------------------------------------

class FakeStream:
    def __init__(self, chunks, content_blocks, stop_reason="end_turn"):
        self._chunks = chunks
        self._blocks = content_blocks
        self._stop_reason = stop_reason

    @property
    def text_stream(self):
        return iter(self._chunks)

    def get_final_message(self):
        msg = MagicMock()
        msg.stop_reason = self._stop_reason
        msg.content = self._blocks
        return msg

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _text_block(text: str):
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_block(name: str, inp: dict, bid: str = "t1"):
    b = MagicMock()
    b.type = "tool_use"
    b.id = bid
    b.name = name
    b.input = inp
    return b


def _make_session(tmp_path: Path):
    from ccenv_pkg.chat import ChatSession
    from ccenv_pkg.config import Config
    from ccenv_pkg.tools import ToolExecutor

    cfg = Config(home=tmp_path)
    s = ChatSession.__new__(ChatSession)
    s.cfg = cfg
    s.agent_name = "test"
    s.manifest = {}
    s.mem_dir = tmp_path / "memory"
    s.mem_dir.mkdir()
    s.model = "claude-sonnet-4-6"
    s.output_dir = tmp_path / "output"
    s.output_dir.mkdir()
    s.client = MagicMock()
    s.executor = ToolExecutor(cfg, s.output_dir)
    s.system_prompt = "System"
    s.conversation_history = []
    s._pending_switch = None
    return s


def _fake_input_factory(*values):
    """Return a fake input() that yields each value, raising if it's an exception type."""
    it = iter(values)

    def _fake(_prompt=""):
        val = next(it)
        if isinstance(val, BaseException):
            raise val
        if isinstance(val, type) and issubclass(val, BaseException):
            raise val()
        return val

    return _fake


# ---------------------------------------------------------------------------
# 1. Two tool_use blocks → history has exactly one user message with both results
# ---------------------------------------------------------------------------

def test_two_tool_blocks_produce_two_results_in_one_message(tmp_path, monkeypatch):
    s = _make_session(tmp_path)

    # Round 1: Claude uses write_file twice
    tb1 = _text_block("Writing two files.")
    tool_a = _tool_block("write_file", {"path": "a.txt", "content": "hello"}, "ta")
    tool_b = _tool_block("write_file", {"path": "b.txt", "content": "world"}, "tb")
    stream1 = FakeStream(["Writing two files."], [tb1, tool_a, tool_b], "tool_use")

    # Round 2: Claude says done
    tb2 = _text_block("Done.")
    stream2 = FakeStream(["Done."], [tb2], "end_turn")

    s.client.messages.stream.side_effect = [stream1, stream2]

    monkeypatch.setattr("builtins.input", _fake_input_factory("write two files", EOFError()))
    s.run_interactive_loop()

    # conversation_history: [user, assistant(text+2 tools), user(2 results), assistant(text)]
    assert len(s.conversation_history) == 4

    assert s.conversation_history[0] == {"role": "user", "content": "write two files"}

    asst = s.conversation_history[1]
    assert asst["role"] == "assistant"
    tool_uses = [b for b in asst["content"] if b.get("type") == "tool_use"]
    assert len(tool_uses) == 2

    results_msg = s.conversation_history[2]
    assert results_msg["role"] == "user"
    results = results_msg["content"]
    assert len(results) == 2
    assert all(r["type"] == "tool_result" for r in results)
    assert {r["tool_use_id"] for r in results} == {"ta", "tb"}

    assert s.conversation_history[3]["role"] == "assistant"

    # Both files actually written
    assert (s.output_dir / "a.txt").read_text() == "hello"
    assert (s.output_dir / "b.txt").read_text() == "world"


# ---------------------------------------------------------------------------
# 2. Tool executor raises an exception → tool_result still appended with status="error"
# ---------------------------------------------------------------------------

def test_executor_exception_still_produces_tool_result(tmp_path, monkeypatch):
    s = _make_session(tmp_path)

    tb1 = _text_block("I'll do it.")
    tool = _tool_block("write_file", {"path": "x.txt", "content": "data"}, "t1")
    stream1 = FakeStream(["I'll do it."], [tb1, tool], "tool_use")

    tb2 = _text_block("I see the tool crashed.")
    stream2 = FakeStream(["I see the tool crashed."], [tb2], "end_turn")

    s.client.messages.stream.side_effect = [stream1, stream2]

    # Patch executor.execute to raise
    s.executor.execute = MagicMock(side_effect=RuntimeError("disk full"))

    monkeypatch.setattr("builtins.input", _fake_input_factory("do something", EOFError()))
    s.run_interactive_loop()

    # Three messages before the final assistant reply
    assert len(s.conversation_history) >= 3

    results_msg = s.conversation_history[2]
    assert results_msg["role"] == "user"
    assert len(results_msg["content"]) == 1

    result_block = results_msg["content"][0]
    assert result_block["type"] == "tool_result"
    assert result_block["tool_use_id"] == "t1"

    data = json.loads(result_block["content"])
    assert data["status"] == "error"
    assert "disk full" in data["message"]


# ---------------------------------------------------------------------------
# 3. User rejects run_command → tool_result with status="rejected_by_user"
# ---------------------------------------------------------------------------

def test_run_command_rejection_produces_rejected_result(tmp_path, monkeypatch):
    s = _make_session(tmp_path)

    tb1 = _text_block("I'll run ls.")
    tool = _tool_block("run_command", {"command": "ls", "reason": "list files"}, "r1")
    stream1 = FakeStream(["I'll run ls."], [tb1, tool], "tool_use")

    tb2 = _text_block("OK, skipping.")
    stream2 = FakeStream(["OK, skipping."], [tb2], "end_turn")

    s.client.messages.stream.side_effect = [stream1, stream2]

    # Inputs: user message → rejection → session exit
    monkeypatch.setattr(
        "builtins.input",
        _fake_input_factory("run a command", "n", EOFError()),
    )
    s.run_interactive_loop()

    results_msg = s.conversation_history[2]
    assert results_msg["role"] == "user"
    result_block = results_msg["content"][0]
    assert result_block["tool_use_id"] == "r1"

    data = json.loads(result_block["content"])
    assert data["status"] == "rejected_by_user"


# ---------------------------------------------------------------------------
# 4a. Validator detects dangling tool_use at end of history and injects synthetic result
# ---------------------------------------------------------------------------

def test_history_validator_injects_synthetic_result(tmp_path):
    s = _make_session(tmp_path)

    # Manually corrupt: assistant has tool_use but no following tool_result
    s.conversation_history = [
        {"role": "user", "content": "do something"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "orphan1", "name": "write_file", "input": {}},
                {"type": "tool_use", "id": "orphan2", "name": "read_file", "input": {}},
            ],
        },
    ]

    s._validate_history()

    # Synthetic user message with tool_results must be injected
    assert len(s.conversation_history) == 3
    injected = s.conversation_history[2]
    assert injected["role"] == "user"
    content = injected["content"]
    assert len(content) == 2
    assert all(b["type"] == "tool_result" for b in content)
    assert {b["tool_use_id"] for b in content} == {"orphan1", "orphan2"}
    for b in content:
        data = json.loads(b["content"])
        assert data["status"] == "lost"


# ---------------------------------------------------------------------------
# 4b. After validation, a subsequent API call succeeds (end-to-end repair)
# ---------------------------------------------------------------------------

def test_corrupted_history_repaired_and_api_call_succeeds(tmp_path, monkeypatch):
    s = _make_session(tmp_path)

    # Pre-corrupt history
    s.conversation_history = [
        {"role": "user", "content": "do something"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "orphan1", "name": "write_file", "input": {}},
            ],
        },
    ]

    # Next user turn: send a follow-up; API responds cleanly
    tb = _text_block("All good!")
    s.client.messages.stream.return_value = FakeStream(["All good!"], [tb], "end_turn")

    monkeypatch.setattr("builtins.input", _fake_input_factory("follow up", EOFError()))
    s.run_interactive_loop()

    # API was called exactly once (for the follow-up)
    assert s.client.messages.stream.call_count == 1

    # History ends with the follow-up exchange; no 400 error means success
    roles = [m["role"] for m in s.conversation_history]
    # The validator injected a synthetic user message, then we appended the new user
    # message and the API responded. Roles must alternate correctly.
    for i in range(len(roles) - 1):
        assert roles[i] != roles[i + 1], (
            f"Consecutive {roles[i]!r} messages at positions {i} and {i+1}: {roles}"
        )


# ---------------------------------------------------------------------------
# 5. /reset clears conversation_history
# ---------------------------------------------------------------------------

def test_reset_command_clears_history(tmp_path, monkeypatch, capsys):
    s = _make_session(tmp_path)

    # Pre-populate history with stale content
    s.conversation_history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]

    # API for the post-reset message
    tb = _text_block("Fresh start!")
    s.client.messages.stream.return_value = FakeStream(["Fresh start!"], [tb], "end_turn")

    monkeypatch.setattr(
        "builtins.input",
        _fake_input_factory("/reset", "new message", EOFError()),
    )
    s.run_interactive_loop()

    out = capsys.readouterr().out
    assert "History reset." in out

    # History must NOT contain the pre-reset stale messages
    assert not any(
        isinstance(m.get("content"), str) and m["content"] == "hello"
        for m in s.conversation_history
    )
    # First message after reset is the new user message
    assert s.conversation_history[0] == {"role": "user", "content": "new message"}
