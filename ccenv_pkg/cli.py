from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import CcenvError, Config
from .commands import cmd_apply, cmd_init, cmd_status, cmd_switch
from .chat import cmd_chat
from .memory import cmd_memory_init, cmd_memory_list, cmd_memory_log, cmd_memory_show


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccenv",
        description="Claude Code environment manager with per-agent memory isolation.",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="Override $HOME (used by the test suite).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create the ccenv working directory.")

    p_apply = sub.add_parser("apply", help="Apply a profile to ~/.claude/ and launch chat.")
    p_apply.add_argument("profile")
    p_apply.add_argument("--no-chat", action="store_true", help="Apply the profile without launching chat.")

    p_switch = sub.add_parser("switch", help="Switch to a different profile and launch chat.")
    p_switch.add_argument("profile")
    p_switch.add_argument("--no-chat", action="store_true", help="Switch profiles without launching chat.")

    sub.add_parser("status", help="Show the active profile.")
    sub.add_parser("chat", help="Start interactive chat with active agent.")

    p_memory = sub.add_parser("memory", help="Agent memory management.")
    memory_sub = p_memory.add_subparsers(dest="memory_command", required=True)

    p_mem_init = memory_sub.add_parser("init", help="Initialize Memory_Logs for an agent.")
    p_mem_init.add_argument("agent")

    p_mem_log = memory_sub.add_parser("log", help="Log a session entry for an agent.")
    p_mem_log.add_argument("agent")
    p_mem_log.add_argument("summary")

    p_mem_show = memory_sub.add_parser("show", help="Show Context.md for an agent.")
    p_mem_show.add_argument("agent")

    memory_sub.add_parser("list", help="List all agents with initialized memory.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    home = args.home if args.home is not None else Path(os.path.expanduser("~"))
    cfg = Config(home=Path(home).expanduser())

    try:
        if args.command == "init":
            return cmd_init(cfg)
        if args.command == "apply":
            return cmd_apply(cfg, args.profile, chat=not args.no_chat)
        if args.command == "switch":
            return cmd_switch(cfg, args.profile, chat=not args.no_chat)
        if args.command == "status":
            return cmd_status(cfg)
        if args.command == "chat":
            return cmd_chat(cfg)
        if args.command == "memory":
            if args.memory_command == "init":
                return cmd_memory_init(cfg, args.agent)
            if args.memory_command == "log":
                return cmd_memory_log(cfg, args.agent, args.summary)
            if args.memory_command == "show":
                return cmd_memory_show(cfg, args.agent)
            if args.memory_command == "list":
                return cmd_memory_list(cfg)
    except CcenvError as exc:
        print(f"ccenv: error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2
