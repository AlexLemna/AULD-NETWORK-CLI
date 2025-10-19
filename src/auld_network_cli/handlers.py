"""Command handlers for the Auld Network CLI."""

from __future__ import annotations

from typing import assert_never

from .commands import command
from .custom_types import Mode
from .logging_config import get_logger
from .shell import Shell


@command("configure", Mode.USER, "Enter privileged configuration mode")
def h_configure(shell: Shell) -> int:
    """Enter admin (privileged) mode from user mode."""
    logger = get_logger("handlers")
    logger.info("Entering privileged configuration mode")
    shell.mode = Mode.ADMIN
    return 0


@command("exit", Mode.ADMIN, "Exit configuration mode")
@command("exit", Mode.USER, "Exit the CLI")
def h_exit(shell: Shell) -> int:
    """Exit from admin mode to user mode, or exit the program if already
    in user mode."""
    logger = get_logger("handlers")
    match shell.mode:
        case Mode.ADMIN:
            # if in admin mode, return to user mode
            logger.info("Exiting configuration mode, returning to user mode")
            shell.mode = Mode.USER
            return 0
        case Mode.USER:
            # already in user mode → exit program
            logger.info("Exiting CLI from user mode")
            raise SystemExit
        case _:
            assert_never(shell.mode)


@command("?", Mode.USER, "Show available commands")
@command("?", Mode.ADMIN, "Show available commands")
def h_help(shell: Shell) -> int:
    """Show all valid commands in the current mode."""
    logger = get_logger("handlers")
    logger.debug(f"Help requested in {shell.mode.value} mode")

    commands = shell.registry._by_mode[shell.mode]
    if not commands:
        print("No commands available in this mode.")
        logger.warning(f"No commands available in {shell.mode.value} mode")
        return 0

    print(f"Available commands in {shell.mode.value} mode:")
    for cmd in sorted(commands, key=lambda c: c.tokens):
        first_column = f"  {' '.join(cmd.tokens)}"
        print(f"{first_column:<30} {cmd.short_description}")

    logger.info(f"Displayed {len(commands)} commands for {shell.mode.value} mode")
    return 0


@command("show", Mode.ADMIN, "Show system information")
def h_show(shell: Shell) -> int:
    """Example admin command."""
    logger = get_logger("handlers")
    logger.info("Show command executed in admin mode")

    print("System status: OK")
    print("Current mode:", shell.mode.value)
    return 0
