"""Tool status display helpers and API message-block converters. Zero ccenv dependencies."""

from __future__ import annotations


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
