"""Core enums and types for the Auld Network CLI."""

from __future__ import annotations

from enum import Enum


class Mode(Enum):
    """The shell modes: user mode and admin (privileged) mode.
    
    This class is used by the shell to determine which commands are 
    available in the current context.
    """

    USER = "user"
    ADMIN = "admin"