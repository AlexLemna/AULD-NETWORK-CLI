"""Auld Network CLI - A command-line interface for network administration."""

from __future__ import annotations

from .cli_args import parse_args, setup_logging_from_args
from .command_types import Command, CommandRegistry, _registry, command
from .commands import cmd_configure, cmd_exit, cmd_help, cmd_show
from .miscellaneous_types import ShellMode
from .program_constants import PROGRAM_CONSTANTS
from .program_exceptions import (
    AmbiguousCommandError,
    BaseCommandError,
    CommandNotFoundError,
)
from .program_logging import log_shutdown, log_startup
from .shell import Shell

__version__ = PROGRAM_CONSTANTS.VERSION
__all__ = [
    "Command",
    "CommandRegistry",
    "_registry",
    "command",
    "AmbiguousCommandError",
    "BaseCommandError",
    "CommandNotFoundError",
    "Shell",
    "ShellMode",
    "cmd_configure",
    "cmd_exit",
    "cmd_help",
    "cmd_show",
    "main",
]


def main() -> None:
    """Main entry point for the CLI application."""
    # Parse command line arguments
    args = parse_args()

    # Set up logging based on arguments
    setup_logging_from_args(args)

    log_startup()

    # Commands are auto-registered when handlers are defined
    try:
        Shell().run()
    except SystemExit:
        log_shutdown()
        raise
    except Exception as e:
        from .program_logging import get_logger

        logger = get_logger("main")
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise
    finally:
        log_shutdown()


if __name__ == "__main__":
    main()
