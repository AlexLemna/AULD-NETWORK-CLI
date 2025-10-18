from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple, assert_never


class Mode(Enum):
    """The shell modes: user mode and admin (privileged) mode. This class is used
    by the shell to determine which commands are available in the current context."""

    USER = "user"
    ADMIN = "admin"


# class ReturnCode(Enum):
#     """Internal codes used by the commands in this CLI. Some of these codes reflect
#     the error codes obtained from the shell scripts this CLI will glue together.
#     Other codes are defined by the programmer for their own purposes."""

"""Custom error classes for the Auld CLI.

I'm defining custom errors here to represent specific error conditions
raised by my code versus errors raised by the rest of Python."""


class BaseCommandError(Exception):
    """This is my base class for errors encountered by my command-line
    interface. Some examples of these errors are:
    - `CommandNotFoundError`
    - `AmbiguousCommandError`
    """


class CommandNotFoundError(BaseCommandError):
    """Raised when a command is not found."""

    pass


class AmbiguousCommandError(BaseCommandError):
    """Raised when a command is ambiguous."""

    pass


@dataclass(frozen=True)
class Command:
    """A definition of a command in the shell."""

    tokens: Tuple[str, ...] | str  # e.g., ("configure",)
    mode: Mode  # "user" or "admin"
    """The mode the command is available within."""

    handler: Callable[["Shell"], int]  # returns 0 for ok, <0 to request shell exit
    short_description: str = "(no help given)"  # brief help text

    def __post_init__(self) -> None:
        """Make sure tokens is a non-empty tuple of strings."""
        match self.tokens:
            case () | "":
                msg = f"This command must have at least one token: {self}"
                raise ValueError(msg)
            case str():
                # Even though our instance is frozen, we can use object.__setattr__
                # to set the value of tokens to a tuple of strings.
                object.__setattr__(self, "tokens", tuple(self.tokens.split()))


class CommandRegistry:
    _instance = None

    def __new__(cls):  # A singleton
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # cls._instance._by_mode = {Mode.USER: [], Mode.ADMIN: []}
        return cls._instance

    def __init__(self) -> None:  # A singleton
        # Only initialize if not already initialized
        if not hasattr(self, "_initialized"):
            self._by_mode: Dict[Mode, List[Command]] = {Mode.USER: [], Mode.ADMIN: []}
            self._initialized = True

    def register(self, cmd: Command) -> None:
        """Registers a `Command` in the `CommandRegistry`."""
        # prevent duplicates on exact tokens
        if any(c.tokens == cmd.tokens for c in self._by_mode[cmd.mode]):
            raise ValueError(
                f"duplicate command in mode {cmd.mode}: {' '.join(cmd.tokens)}"
            )
        self._by_mode[cmd.mode].append(cmd)

    def _candidates_for_prefix(
        self, mode: Mode, input_tokens: Sequence[str]
    ) -> List[Command]:
        out: List[Command] = []
        for c in self._by_mode[mode]:
            if len(input_tokens) > len(c.tokens):
                continue
            ok = True
            for i, t in enumerate(input_tokens):
                if not c.tokens[i].startswith(t):
                    ok = False
                    break
            if ok:
                out.append(c)
        return out

    def resolve(self, mode: Mode, input_tokens: Sequence[str]) -> Command:
        if not input_tokens:
            raise ValueError("empty input")
        matches = self._candidates_for_prefix(mode, input_tokens)
        # require that all command tokens are fully specified (by prefix) and unique
        full_matches = [m for m in matches if len(input_tokens) == len(m.tokens)]
        if not full_matches:
            # could be incomplete or unknown; provide best diagnostics
            if not matches:
                raise ValueError(f'unknown command: "{" ".join(input_tokens)}"')
            # user typed a prefix of a longer command
            needed = ", ".join(" ".join(m.tokens) for m in matches[:10])
            raise ValueError(f"incomplete command. did you mean: {needed}")
        if len(full_matches) > 1:
            alts = ", ".join(" ".join(m.tokens) for m in full_matches[:10])
            raise ValueError(f"ambiguous command: {alts}")
        return full_matches[0]


# Global registry instance for auto-registration
_registry = CommandRegistry()


def command(
    tokens: Tuple[str, ...] | str, mode: Mode, description: str = "(no help given)"
):
    """Decorator to auto-register command handlers."""

    def decorator(func: Callable[["Shell"], int]) -> Callable[["Shell"], int]:
        # Convert string to tuple if needed
        token_tuple = (tokens,) if isinstance(tokens, str) else tokens
        cmd = Command(
            tokens=token_tuple, mode=mode, handler=func, short_description=description
        )
        _registry.register(cmd)
        return func

    return decorator


class Shell:
    """The command-line shell object. This keeps track of the current mode
    (`Shell.mode`) and the registry (`Shell.registry`) of all the commands
    defined in the source code with the `@command` flag.

    The main REPL loop is implemented in `Shell.run()`, and the prompt string
    is generated by `Shell.prompt()`."""

    def __init__(self, registry: Optional[CommandRegistry] = None) -> None:
        self.registry = registry or _registry
        self.mode: Mode = Mode.USER

    def prompt(self) -> str:
        """Returns the prompt string based on current mode. If `Mode.USER`,
        use '>'; if `Mode.ADMIN`, use '#'."""
        text = "Auld CLI"
        match self.mode:
            case Mode.USER:
                text += ">"
            case Mode.ADMIN:
                text += "#"
            case _:
                # This should never happen. We use `assert_never` to
                # tell type checkers that this branch should be unreachable.
                assert_never(self.mode)
        return f"{text} "

    def run(self) -> int:
        """Run the main REPL loop. Returns an exit code where 0 indicates
        success and 1 indicates failure."""
        while True:
            try:
                line = input(self.prompt())
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                print()
                continue

            line = line.strip()
            # If empty line, just reprompt. Otherwise, split
            # into tokens at whitespaces and try to resolve.
            if not line:
                continue  # start the loop over again
            else:
                tokens = line.split()

            # Resolve and execute
            try:
                cmd = self.registry.resolve(self.mode, tokens)
            except ValueError as e:
                print(e)
                continue

            rc = 0
            try:
                rc = cmd.handler(self)
            except Exception as e:
                print(f"handler error: {e}")
                rc = 1

            if rc < 0:
                return 0


# ---- Handlers -------------------------------------------------------------


@command("configure", Mode.USER, "Enter privileged configuration mode")
def h_configure(shell: Shell) -> int:
    """Enter admin (privileged) mode from user mode."""
    shell.mode = Mode.ADMIN
    return 0


@command("exit", Mode.ADMIN, "Exit configuration mode")
@command("exit", Mode.USER, "Exit the CLI")
def h_exit(shell: Shell) -> int:
    """Exit from admin mode to user mode, or exit the program if already
    in user mode."""
    match shell.mode:
        case Mode.ADMIN:
            # if in admin mode, return to user mode
            shell.mode = Mode.USER
            return 0
        case Mode.USER:
            # already in user mode → exit program
            raise SystemExit
        case _:
            assert_never(shell.mode)


@command("?", Mode.USER, "Show available commands")
@command("?", Mode.ADMIN, "Show available commands")
def h_help(shell: Shell) -> int:
    """Show all valid commands in the current mode."""
    commands = shell.registry._by_mode[shell.mode]
    if not commands:
        print("No commands available in this mode.")
        return 0

    print(f"Available commands in {shell.mode.value} mode:")
    for cmd in sorted(commands, key=lambda c: c.tokens):
        first_column = f"  {' '.join(cmd.tokens)}"
        print(f"{first_column:<30} {cmd.short_description}")
    return 0


@command("show", Mode.ADMIN, "Show system information")
def h_show(shell: Shell) -> int:
    """Example admin command."""
    print("System status: OK")
    print("Current mode:", shell.mode.value)
    return 0


# ---- Wiring ---------------------------------------------------------------


def main() -> int:
    # Commands are auto-registered when handlers are defined
    shell = Shell()
    return shell.run()


if __name__ == "__main__":
    raise SystemExit(main())
