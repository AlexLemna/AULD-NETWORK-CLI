"""Command line argument parsing for the Auld Network CLI."""

from __future__ import annotations

import argparse
from logging import getLevelName
from pathlib import Path
from typing import Optional

from .program_constants import DEFAULT_LOG_FILE, DEFAULT_LOG_LEVEL


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line arguments for the CLI.

    Args:
        args: List of arguments to parse. If None, uses sys.argv.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        prog="auld-network-cli",
        description="A command-line interface for network administration",
        epilog="Environment variables: None.",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=DEFAULT_LOG_LEVEL,
        help=f"Set the logging level (default: {getLevelName(DEFAULT_LOG_LEVEL)})",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        default=DEFAULT_LOG_FILE,
        help="Path to log file (default: logs/cli.log)",
    )

    parser.add_argument(
        "--no-console-log",
        action="store_true",
        help="Disable console logging (only log to file)",
    )

    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    return parser.parse_args(args)


def setup_logging_from_args(args: argparse.Namespace) -> None:
    """Set up logging based on parsed command line arguments.

    Args:
        args: Parsed arguments from parse_args()
    """
    from .program_logging import setup_logging

    # Create logs directory if logging to file
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize logging
    setup_logging(
        level=args.log_level,
        log_file=args.log_file,
        console_output=False if args.no_console_log else True,
    )
