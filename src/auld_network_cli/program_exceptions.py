"""Core exceptions for the Auld Network CLI."""

from __future__ import annotations


class BaseCommandError(Exception):
    """Base class for errors encountered by the command-line interface.
    
    Some examples of these errors are:
    - `CommandNotFoundError`
    - `AmbiguousCommandError`
    """


class CommandNotFoundError(BaseCommandError):
    """Raised when a command is not found."""


class AmbiguousCommandError(BaseCommandError):
    """Raised when a command is ambiguous."""