"""Auld Network CLI - A command-line interface for network administration."""

from __future__ import annotations

from . import handlers  # noqa: F401
from .cli_args import parse_args, setup_logging_from_args
from .commands import Command, CommandRegistry, _registry, command
from .custom_types import Mode
from .exceptions import AmbiguousCommandError, BaseCommandError, CommandNotFoundError
from .handlers import h_configure, h_exit, h_help, h_show
from .logging_config import log_shutdown, log_startup
from .shell import Shell

__version__ = "0.1.0"
__all__ = [
    "Command",
    "CommandRegistry",
    "_registry",
    "command",
    "AmbiguousCommandError",
    "BaseCommandError",
    "CommandNotFoundError",
    "Shell",
    "Mode",
    "h_configure",
    "h_exit",
    "h_help",
    "h_show",
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
        from .logging_config import get_logger

        logger = get_logger("main")
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise
    finally:
        log_shutdown()


if __name__ == "__main__":
    main()
