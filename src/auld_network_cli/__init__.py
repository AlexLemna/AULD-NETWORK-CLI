"""Auld Network CLI - A command-line interface for network administration."""

from __future__ import annotations

from .commands import Command, CommandRegistry, _registry, command
from .exceptions import AmbiguousCommandError, BaseCommandError, CommandNotFoundError
from .handlers import h_configure, h_exit, h_help, h_show
from .shell import Shell
from .types import Mode

# Import handlers to ensure they are registered
from . import handlers  # noqa: F401

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
    # Commands are auto-registered when handlers are defined
    try:
        Shell().run()
    except SystemExit:
        raise


if __name__ == "__main__":
    main()