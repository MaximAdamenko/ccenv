from __future__ import annotations

import datetime
import sys
from pathlib import Path

from .config import Config

MEMORY_FILES = ("Context.md", "Checkpoint.md", "Lessons.md", "Preferences.md")

_CONTEXT_TEMPLATE = """\
# Context — {agent}
**Last updated:** {date}

*Quick startup snapshot. Read this first instead of scanning all memory files.*

---

## Project Summary
[To be filled after first session]

## Current Task
No active task.

## Recent Lessons
None yet.

## Active Preferences
None yet.

## My Recent Sessions
None yet.
"""

_CHECKPOINT_TEMPLATE = """\
# Checkpoint — {agent}

*Save/resume complex tasks here.*

---

## Status
No active task.

## Last Task
None.
"""

_LESSONS_TEMPLATE = """\
# Lessons Learned — {agent}

*Mistakes to avoid, patterns that worked. Append-only — never delete.*

---

<!-- Template for new entries:

## [YYYY-MM-DD] - [Brief title]
- **Context:** [what happened]
- **Lesson:** [what to remember]
- **Apply when:** [future trigger]

-->
"""

_PREFERENCES_TEMPLATE = """\
# Preferences — {agent}

*How the user likes things done. Append-only — never delete.*

---

<!-- Template for new entries:

## [Category]
*[YYYY-MM-DD]*
- **Preference:** [detail]

-->
"""


def ensure_agent_memory(cfg: Config, name: str) -> Path:
    mem_dir = cfg.agent_memory_dir(name)
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "Sessions").mkdir(exist_ok=True)
    (mem_dir / "Notes").mkdir(exist_ok=True)
    (mem_dir / "Archive").mkdir(exist_ok=True)

    today = datetime.date.today().isoformat()
    scaffolds = {
        "Context.md": _CONTEXT_TEMPLATE.format(agent=name, date=today),
        "Checkpoint.md": _CHECKPOINT_TEMPLATE.format(agent=name),
        "Lessons.md": _LESSONS_TEMPLATE.format(agent=name),
        "Preferences.md": _PREFERENCES_TEMPLATE.format(agent=name),
    }
    for fname, content in scaffolds.items():
        target = mem_dir / fname
        if not target.exists():
            target.write_text(content, encoding="utf-8")

    return mem_dir


def append_session(mem_dir: Path, agent: str, summary: str) -> Path:
    today = datetime.date.today().isoformat()
    session_file = mem_dir / "Sessions" / f"Session_{today}.md"
    header = f"# Session — {today}\n\n**Agent:** {agent}\n\n---\n\n"
    entry = f"## Entry\n{summary}\n\n---\n"
    if session_file.exists():
        with session_file.open("a", encoding="utf-8") as f:
            f.write(entry)
    else:
        session_file.write_text(header + entry, encoding="utf-8")
    return session_file


def cmd_memory_init(cfg: Config, name: str) -> int:
    mem_dir = ensure_agent_memory(cfg, name)
    print(f"Memory initialized for agent '{name}' at {mem_dir}")
    return 0


def cmd_memory_log(cfg: Config, name: str, summary: str) -> int:
    mem_dir = ensure_agent_memory(cfg, name)
    sf = append_session(mem_dir, name, summary)
    print(f"Logged session for '{name}' → {sf}")
    return 0


def cmd_memory_show(cfg: Config, name: str) -> int:
    mem_dir = cfg.agent_memory_dir(name)
    ctx = mem_dir / "Context.md"
    if not ctx.is_file():
        print(f"No memory found for agent '{name}'. Run: ccenv memory init {name}",
              file=sys.stderr)
        return 1
    print(ctx.read_text(encoding="utf-8"))
    return 0


def cmd_memory_list(cfg: Config) -> int:
    agents_dir = cfg.agents_dir
    if not agents_dir.is_dir():
        print("No agents with memory yet. Run: ccenv memory init <agent>")
        return 0
    agents = sorted(p.name for p in agents_dir.iterdir() if p.is_dir())
    if not agents:
        print("No agents with memory yet.")
    else:
        print("Agents with isolated memory:")
        for a in agents:
            print(f"  {a}  →  {cfg.agent_memory_dir(a)}")
    return 0
