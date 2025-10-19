"""Command handlers for the Auld Network CLI."""

from __future__ import annotations

from typing import assert_never

from .command_types import command
from .miscellaneous_types import ShellMode
from .program_logging import get_logger
from .shell import Shell


@command("configure", ShellMode.USER, "Enter privileged configuration mode")
def cmd_configure(shell: Shell) -> int:
    """Enter admin (privileged) mode from user mode."""
    logger = get_logger("commands")
    logger.info("Entering privileged configuration mode")
    shell.mode = ShellMode.ADMIN
    return 0


@command("exit", ShellMode.ADMIN, "Exit configuration mode")
@command("exit", ShellMode.USER, "Exit the CLI")
def cmd_exit(shell: Shell) -> int:
    """Exit from admin mode to user mode, or exit the program if already
    in user mode."""
    logger = get_logger("commands")
    match shell.mode:
        case ShellMode.ADMIN:
            # if in admin mode, return to user mode
            logger.info("Exiting configuration mode, returning to user mode")
            shell.mode = ShellMode.USER
            return 0
        case ShellMode.USER:
            # already in user mode → exit program
            logger.info("Exiting CLI from user mode")
            raise SystemExit
        case _:
            assert_never(shell.mode)


@command("?", ShellMode.USER, "Show available commands")
@command("?", ShellMode.ADMIN, "Show available commands")
def cmd_help(shell: Shell) -> int:
    """Show all valid commands in the current mode."""
    logger = get_logger("commands")
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


@command("show", ShellMode.ADMIN, "Show system information")
def cmd_show(shell: Shell) -> int:
    """Example admin command."""
    logger = get_logger("commands")
    logger.info("Show command executed in admin mode")

    print("System status: OK")
    print("Current mode:", shell.mode.value)
    return 0
