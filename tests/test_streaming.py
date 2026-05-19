"""Tests for streaming, tool status display, and spinner behaviour."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeStream:
    """Minimal context-manager mock for client.messages.stream(...)."""

    def __init__(
        self,
        chunks: list[str],
        content_blocks: list,
        stop_reason: str = "end_turn",
    ) -> None:
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
    """Build a ChatSession bypassing __init__ — no real API key or profile needed."""
    from ccenv_pkg.ccenvManager import ChatSession
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


# ---------------------------------------------------------------------------
# 1. Streamed text assembles correctly in conversation_history
# ---------------------------------------------------------------------------

def test_streamed_text_assembles_in_history(tmp_path, monkeypatch):
    s = _make_session(tmp_path)

    chunks = ["Hello", ", ", "world", "!"]
    full_text = "Hello, world!"
    tb = _text_block(full_text)
    stream = FakeStream(chunks, [tb], "end_turn")
    s.client.messages.stream.return_value = stream

    inputs = iter(["hi there", EOFError()])

    def fake_input(_prompt=""):
        val = next(inputs)
        if isinstance(val, type) and issubclass(val, BaseException):
            raise val()
        if isinstance(val, BaseException):
            raise val
        return val

    monkeypatch.setattr("builtins.input", fake_input)
    s.run_interactive_loop()

    assert s.conversation_history[0] == {"role": "user", "content": "hi there"}
    assistant = s.conversation_history[1]
    assert assistant["role"] == "assistant"
    texts = [b["text"] for b in assistant["content"] if b.get("type") == "text"]
    assert texts == [full_text]


# ---------------------------------------------------------------------------
# 2. Tool status prefix appears in captured stdout
# ---------------------------------------------------------------------------

def test_tool_status_prefix_in_output(tmp_path, monkeypatch, capsys):
    s = _make_session(tmp_path)

    # Round 1: Claude uses write_file
    tb1 = _text_block("Writing now.")
    tool = _tool_block("write_file", {"path": "out.txt", "content": "data"})
    stream1 = FakeStream(["Writing now."], [tb1, tool], "tool_use")

    # Round 2: Claude says done
    tb2 = _text_block("Done.")
    stream2 = FakeStream(["Done."], [tb2], "end_turn")

    call_streams = [stream1, stream2]
    s.client.messages.stream.side_effect = call_streams

    inputs = iter(["write a file", EOFError()])

    def fake_input(_prompt=""):
        val = next(inputs)
        if isinstance(val, EOFError):
            raise val
        return val

    monkeypatch.setattr("builtins.input", fake_input)
    s.run_interactive_loop()

    out = capsys.readouterr().out
    assert "⏺ Writing file: out.txt" in out
    assert (s.output_dir / "out.txt").read_text() == "data"


# ---------------------------------------------------------------------------
# 3. No ANSI escape codes in non-TTY mode (pytest captures stdout → isatty=False)
# ---------------------------------------------------------------------------

def test_no_ansi_codes_in_non_tty(tmp_path, monkeypatch, capsys):
    s = _make_session(tmp_path)

    tb = _text_block("Hello!")
    stream = FakeStream(["Hello!"], [tb], "end_turn")
    s.client.messages.stream.return_value = stream

    inputs = iter(["hello", EOFError()])

    def fake_input(_prompt=""):
        val = next(inputs)
        if isinstance(val, EOFError):
            raise val
        return val

    monkeypatch.setattr("builtins.input", fake_input)
    s.run_interactive_loop()

    out = capsys.readouterr().out
    assert "\033[" not in out
    assert "Hello!" in out


# ---------------------------------------------------------------------------
# 4. Spinner is a no-op outside a TTY (no output, no threads left running)
# ---------------------------------------------------------------------------

def test_spinner_noop_outside_tty(tmp_path, monkeypatch):
    from ccenv_pkg.ccenvManager import Spinner

    # Ensure isatty returns False
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    spinner = Spinner()
    assert not spinner._tty
    spinner.start("test")
    assert spinner._thread is None  # no thread started
    spinner.stop()  # must not raise


# ---------------------------------------------------------------------------
# 5. _tool_status_label and _tool_status_detail helpers
# ---------------------------------------------------------------------------

def test_tool_status_label_variants():
    from ccenv_pkg.ccenvManager import _tool_status_label

    assert _tool_status_label("write_file", {"path": "a.txt"}) == "Writing file: a.txt"
    assert _tool_status_label("read_file", {"path": "b.txt"}) == "Reading file: b.txt"
    assert _tool_status_label("list_files", {}) == "Listing: ."
    assert _tool_status_label("run_command", {"command": "ls"}) == "Running: ls"
    assert _tool_status_label("open_file", {"path": "c.html"}) == "Opening: c.html"
    assert _tool_status_label("switch_agent", {"name": "devops"}) == "Switching to: devops"


def test_tool_status_detail_success():
    from ccenv_pkg.ccenvManager import _tool_status_detail

    assert "KB" in _tool_status_detail("write_file", {"status": "success", "bytes_written": 2048})
    assert "B" in _tool_status_detail("write_file", {"status": "success", "bytes_written": 50})
    assert "lines" in _tool_status_detail("read_file", {"status": "success", "content": "a\nb\nc"})
    assert "entries" in _tool_status_detail("list_files", {"status": "success", "entries": [1, 2], "truncated": False})
    assert "exit 0" in _tool_status_detail("run_command", {"status": "success", "return_code": 0})
    assert "exit 1" in _tool_status_detail("run_command", {"status": "success", "return_code": 1})
    assert "opened" in _tool_status_detail("open_file", {"status": "success"})


def test_tool_status_detail_error():
    from ccenv_pkg.ccenvManager import _tool_status_detail

    r = _tool_status_detail("write_file", {"status": "error", "message": "no space"})
    assert r.startswith("✗")
    assert "no space" in r


def test_tool_status_detail_rejected():
    from ccenv_pkg.ccenvManager import _tool_status_detail

    r = _tool_status_detail("run_command", {"status": "rejected_by_user"})
    assert "rejected" in r
