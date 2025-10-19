"""Logging configuration for the Auld Network CLI."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str | int = "INFO",
    log_file: Optional[str] = None,
    console_output: bool = True,
) -> logging.Logger:
    """Set up logging for the Auld Network CLI.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file. If None, no file logging.
        console_output: Whether to log to console
        detailed: Whether to use detailed format with timestamps

    Returns:
        Configured logger instance
    """
    # Get the root logger for our package
    logger = logging.getLogger("auld_network_cli")

    # Clear any existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Set the logging level
    if isinstance(level, str):
        numeric_level = getattr(logging, level.upper(), logging.INFO)
    else:
        numeric_level = level
    logger.setLevel(numeric_level)

    # Create formatters
    console_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_format = (
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )

    console_formatter = logging.Formatter(console_format)
    file_formatter = logging.Formatter(file_format)

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(console_formatter)
        # Only show WARNING and above on console by default unless in debug mode
        if numeric_level <= logging.DEBUG:
            console_handler.setLevel(logging.DEBUG)
        else:
            console_handler.setLevel(logging.WARNING)
        logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Use rotating file handler to prevent log files from getting too large
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(numeric_level)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "") -> logging.Logger:
    """Get a logger for a specific module.

    Args:
        name: Module name (will be prefixed with 'auld_network_cli.')

    Returns:
        Logger instance
    """
    if name:
        full_name = f"auld_network_cli.{name}"
    else:
        full_name = "auld_network_cli"

    return logging.getLogger(full_name)


def log_command_execution(command_tokens: list[str], mode: str, success: bool) -> None:
    """Log command execution details.

    Args:
        command_tokens: The command tokens that were executed
        mode: The shell mode (user/admin)
        success: Whether the command executed successfully
    """
    logger = get_logger("commands")
    command_str = " ".join(command_tokens)

    if success:
        logger.info(f"Command executed successfully: '{command_str}' in {mode} mode")
    else:
        logger.warning(f"Command failed: '{command_str}' in {mode} mode")


def log_mode_change(old_mode: str, new_mode: str) -> None:
    """Log shell mode changes.

    Args:
        old_mode: Previous mode
        new_mode: New mode
    """
    logger = get_logger("shell")
    logger.info(f"Mode changed: {old_mode} -> {new_mode}")


def log_startup() -> None:
    """Log application startup."""
    logger = get_logger("main")
    logger.info("Auld Network CLI starting up")


def log_shutdown() -> None:
    """Log application shutdown."""
    logger = get_logger("main")
    logger.info("Auld Network CLI shutting down")
