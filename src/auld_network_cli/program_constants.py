"""program_constants.py

The `program_constants` module. The values in this file are all *at least*
constant during a single run of the program, though many (like the logging
directory, for example) will vary between installations and operating
systems.
"""

from dataclasses import dataclass
from importlib.metadata import version
from logging import INFO, WARNING

import platformdirs

# Normally we'd like to define the name of the program in the
# PROGRAM_CONSTANTS dataclass below. But, since we're also going to be
# using the name to get the version from package metadata, we need
# to define it here first.
_name = "auld-network-cli"


@dataclass(frozen=True, slots=True)
class PROGRAM_CONSTANTS:
    NAME: str = _name
    """The name of the program. This is used when creating directory
    structures using `platformdirs`"""

    AUTHOR: str = "AULD"
    """The author/publisher of the program. This is used when creating 
    directory structures using `platformdirs`"""

    LOCAL_TESTING_MODE: bool = True
    """If this is true, then the program should not make any filesystem
    changes outside of its own directory structure."""

    VERSION: str = version(_name)
    """The current version of the program, as read from package metadata."""


DEFAULT_LOG_DIR = platformdirs.user_log_path(
    appname="Auld",
    # appauthor=PROGRAM_CONSTANTS.AUTHOR,
    ensure_exists=True,
)


DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "default.log"
DEFAULT_LOG_LEVEL = WARNING

# DEFAULT_CONSOLE_LOG_LEVEL = WARNING
# DEFAULT_FILE_LOG_LEVEL = INFO
