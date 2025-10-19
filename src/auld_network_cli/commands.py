"""Command definition and registry for the Auld Network CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, Tuple

from .types import Mode

if TYPE_CHECKING:
    from .shell import Shell


@dataclass(frozen=True)
class Command:
    """A definition of a command in the shell."""

    tokens: Tuple[str, ...] | str  # e.g., ("configure",)
    mode: Mode  # "user" or "admin"
    """The mode the command is available within."""

    handler: Callable[[Shell], int]  # returns 0 for ok, <0 to request shell exit
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
    """Registry for CLI commands with singleton pattern."""
    
    _instance = None

    def __new__(cls):  # A singleton
        if cls._instance is None:
            cls._instance = super().__new__(cls)
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
        """Find commands that match the given input tokens as prefix."""
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
        """Resolve input tokens to a specific command."""
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

    def decorator(func: Callable[[Shell], int]) -> Callable[[Shell], int]:
        
        # Convert string to tuple if needed
        token_tuple = (tokens,) if isinstance(tokens, str) else tokens
        cmd = Command(
            tokens=token_tuple, mode=mode, handler=func, short_description=description
        )
        _registry.register(cmd)
        return func

    return decorator