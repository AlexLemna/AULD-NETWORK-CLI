"""Command handlers for the Auld Network CLI."""

from __future__ import annotations

from typing import assert_never

from .commands import command
from .shell import Shell
from .types import Mode


@command("configure", Mode.USER, "Enter privileged configuration mode")
def h_configure(shell: Shell) -> int:
    """Enter admin (privileged) mode from user mode."""
    shell.mode = Mode.ADMIN
    return 0


@command("exit", Mode.ADMIN, "Exit configuration mode")
@command("exit", Mode.USER, "Exit the CLI")
def h_exit(shell: Shell) -> int:
    """Exit from admin mode to user mode, or exit the program if already
    in user mode."""
    match shell.mode:
        case Mode.ADMIN:
            # if in admin mode, return to user mode
            shell.mode = Mode.USER
            return 0
        case Mode.USER:
            # already in user mode → exit program
            raise SystemExit
        case _:
            assert_never(shell.mode)


@command("?", Mode.USER, "Show available commands")
@command("?", Mode.ADMIN, "Show available commands")
def h_help(shell: Shell) -> int:
    """Show all valid commands in the current mode."""
    commands = shell.registry._by_mode[shell.mode]
    if not commands:
        print("No commands available in this mode.")
        return 0

    print(f"Available commands in {shell.mode.value} mode:")
    for cmd in sorted(commands, key=lambda c: c.tokens):
        first_column = f"  {' '.join(cmd.tokens)}"
        print(f"{first_column:<30} {cmd.short_description}")
    return 0


@command("show", Mode.ADMIN, "Show system information")
def h_show(shell: Shell) -> int:
    """Example admin command."""
    print("System status: OK")
    print("Current mode:", shell.mode.value)
    return 0