from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple


class Mode(Enum):
    USER = "user"
    ADMIN = "admin"


@dataclass(frozen=True)
class Command:
    tokens: Tuple[str, ...]  # e.g., ("configure",)
    mode: Mode  # "user" or "admin"
    handler: Callable[["Shell"], int]  # returns 0 for ok, <0 to request shell exit
    short_description: str = "(no help given)"  # brief help text


class CommandRegistry:
    _instance = None

    def __new__(cls):  # A singleton
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._by_mode = {Mode.USER: [], Mode.ADMIN: []}
        return cls._instance

    def __init__(self) -> None:  # A singleton
        # Only initialize if not already initialized
        if not hasattr(self, "_initialized"):
            self._by_mode: Dict[Mode, List[Command]] = {Mode.USER: [], Mode.ADMIN: []}
            self._initialized = True

    def register(self, cmd: Command) -> None:
        if cmd.mode not in self._by_mode:
            raise ValueError("unknown mode")
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
    def __init__(self, registry: Optional[CommandRegistry] = None) -> None:
        self.registry = registry or _registry
        self.mode: Mode = Mode.USER

    def prompt(self) -> str:
        return "cli# " if self.mode == Mode.ADMIN else "cli> "

    def run(self) -> int:
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
            if not line:
                continue

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
    shell.mode = Mode.ADMIN
    return 0


@command("exit", Mode.ADMIN, "Exit configuration mode")
@command("exit", Mode.USER, "Exit the CLI")
def h_exit(shell: Shell) -> int:
    if shell.mode == Mode.ADMIN:
        shell.mode = Mode.USER
        return 0
    # already in user mode → exit program
    return -1


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
