"""Tool definitions and executor for ccenv chat sessions."""

from __future__ import annotations

import platform
import shlex
import subprocess
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config

# ccenv project root — the allowed read-only tree for read_file / list_files
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "write_file",
        "description": (
            "Write content to a file under the agent's output directory. "
            "The path must be relative — absolute paths and '../' traversals are rejected. "
            "Parent directories are created automatically. "
            "Cannot write outside the output directory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative file path inside the output directory.",
                },
                "content": {
                    "type": "string",
                    "description": "Full text content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a file from the agent's output directory or the ccenv project root. "
            "Cannot read files outside those two areas. "
            "Returns file content as text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "List directory contents from the output directory or project root. "
            "Returns at most 200 entries (non-recursive). "
            "Omit 'path' to list the output directory root."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to list (relative path). Defaults to output root.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Propose a shell command for the user to approve before running. "
            "The user sees the command and reason, then types y/N. "
            "On approval, runs via subprocess and returns stdout/stderr/return_code. "
            "Returns {'status': 'rejected_by_user'} if the user declines. "
            "Cannot run commands without user approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run.",
                },
                "reason": {
                    "type": "string",
                    "description": "Why this command is needed — shown to the user before they approve.",
                },
            },
            "required": ["command", "reason"],
        },
    },
    {
        "name": "open_file",
        "description": (
            "Open a file from the output directory with the default system application (macOS only). "
            "Useful for previewing HTML in a browser. "
            "Cannot open files outside the output directory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from the output directory.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "switch_agent",
        "description": (
            "Exit this agent and apply a different ccenv profile, starting a fresh conversation. "
            "The current session is saved to memory before switching. "
            "Returns an error if the target profile does not exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the ccenv profile to switch to (e.g. 'devops', 'frontend').",
                },
            },
            "required": ["name"],
        },
    },
]


class ToolExecutor:
    """Executes tool calls from Claude. Never raises — all errors are returned as dicts."""

    def __init__(self, cfg: "Config", output_dir: Path) -> None:
        self.cfg = cfg
        self.output_dir = output_dir.resolve()
        self.project_root = _PROJECT_ROOT.resolve()

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return {"status": "error", "message": f"Unknown tool: {tool_name!r}"}
        try:
            return handler(tool_input)
        except Exception as exc:
            return {"status": "error", "message": f"Unexpected error in {tool_name}: {exc}"}

    # ------------------------------------------------------------------ path helpers

    def _resolve_write(self, path_str: str) -> tuple[Path | None, str | None]:
        if "\x00" in path_str:
            return None, "Path contains null byte"
        if Path(path_str).is_absolute():
            return None, "Absolute paths are not allowed; use a path relative to the output directory"
        try:
            resolved = (self.output_dir / path_str).resolve()
        except Exception as exc:
            return None, f"Invalid path: {exc}"
        if not resolved.is_relative_to(self.output_dir):
            return None, f"Path traversal rejected: {path_str!r} escapes the output directory"
        return resolved, None

    def _resolve_read(self, path_str: str) -> tuple[Path | None, str | None]:
        if "\x00" in path_str:
            return None, "Path contains null byte"
        if Path(path_str).is_absolute():
            return None, "Absolute paths are not allowed"
        for base in (self.output_dir, self.project_root):
            try:
                candidate = (base / path_str).resolve()
                if candidate.is_relative_to(base) and candidate.is_file():
                    return candidate, None
            except Exception:
                continue
        return None, f"File not found in output directory or project root: {path_str!r}"

    def _resolve_dir(self, path_str: str) -> tuple[Path | None, str | None]:
        if not path_str:
            return self.output_dir, None
        if "\x00" in path_str:
            return None, "Path contains null byte"
        if Path(path_str).is_absolute():
            return None, "Absolute paths are not allowed"
        for base in (self.output_dir, self.project_root):
            try:
                candidate = (base / path_str).resolve()
                if candidate.is_relative_to(base) and candidate.is_dir():
                    return candidate, None
            except Exception:
                continue
        return None, f"Directory not found: {path_str!r}"

    # ------------------------------------------------------------------ tools

    def _tool_write_file(self, inp: dict) -> dict:
        path_str = inp.get("path", "")
        content = inp.get("content", "")
        resolved, err = self._resolve_write(path_str)
        if err:
            return {"status": "error", "message": err}
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return {"status": "success", "path": str(resolved), "bytes_written": len(content.encode())}

    def _tool_read_file(self, inp: dict) -> dict:
        path_str = inp.get("path", "")
        resolved, err = self._resolve_read(path_str)
        if err:
            return {"status": "error", "message": err}
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"status": "error", "message": f"Cannot read file: {exc}"}
        return {
            "status": "success",
            "path": str(resolved),
            "content": content,
            "size_bytes": resolved.stat().st_size,
        }

    def _tool_list_files(self, inp: dict) -> dict:
        path_str = inp.get("path") or ""
        resolved, err = self._resolve_dir(path_str)
        if err:
            return {"status": "error", "message": err}
        entries = []
        try:
            for item in sorted(resolved.iterdir()):
                entries.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size_bytes": item.stat().st_size if item.is_file() else None,
                })
                if len(entries) >= 200:
                    break
        except OSError as exc:
            return {"status": "error", "message": f"Cannot list directory: {exc}"}
        return {
            "status": "success",
            "directory": str(resolved),
            "entries": entries,
            "truncated": len(entries) == 200,
        }

    def _tool_run_command(self, inp: dict) -> dict:
        command = inp.get("command", "").strip()
        reason = inp.get("reason", "").strip()
        if not command:
            return {"status": "error", "message": "No command provided"}

        print(f"\n{'─' * 60}")
        print(f"  Command : {command}")
        print(f"  Reason  : {reason or '(no reason given)'}")
        print(f"{'─' * 60}")
        try:
            answer = input("Run this command? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"

        if answer != "y":
            print("Command rejected.")
            return {"status": "rejected_by_user"}

        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return {"status": "error", "message": f"Cannot parse command: {exc}"}

        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            return {"status": "error", "message": f"Executable not found: {argv[0]!r}"}
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Command timed out after 120 s"}
        except OSError as exc:
            return {"status": "error", "message": f"OS error: {exc}"}

        return {
            "status": "success",
            "return_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    def _tool_open_file(self, inp: dict) -> dict:
        if platform.system() != "Darwin":
            return {"status": "error", "message": "open_file is only available on macOS"}
        path_str = inp.get("path", "")
        resolved, err = self._resolve_write(path_str)
        if err:
            return {"status": "error", "message": err}
        if not resolved.exists():
            return {"status": "error", "message": f"File not found: {path_str!r}"}
        try:
            subprocess.run(["open", str(resolved)], check=True, timeout=10)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return {"status": "error", "message": f"open failed: {exc}"}
        return {"status": "success", "path": str(resolved)}

    def _tool_switch_agent(self, inp: dict) -> dict:
        name = inp.get("name", "").strip()
        if not name:
            return {"status": "error", "message": "Profile name is required"}
        profile_dir = self.cfg.profiles_dir / name
        if not profile_dir.is_dir():
            available = (
                sorted(p.name for p in self.cfg.profiles_dir.iterdir() if p.is_dir())
                if self.cfg.profiles_dir.is_dir()
                else []
            )
            return {
                "status": "error",
                "message": f"Profile '{name}' not found. Available: {', '.join(available) or 'none'}",
            }
        return {"status": "switch_agent", "name": name}
