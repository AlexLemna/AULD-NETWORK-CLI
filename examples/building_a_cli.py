#!/usr/bin/env python3
"""
Cisco-like interactive CLI with argparse and dataclass-defined commands.

Features
- Two modes: user (">") and admin ("#")
- Flat command space per mode; multi-word commands supported
- Unambiguous abbreviations: "sho ip int bri" -> "show ip interface brief"
- Tab completion via readline if available (on Windows you may need pyreadline3)
- Declarative ArgSpec/Command definitions auto-built into argparse parsers
- Stateless handlers (print-only) for demonstration

Standard library only.
"""

from __future__ import annotations

import argparse
import shlex
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Sequence, Tuple

# Optional tab completion
try:
    import readline  # type: ignore
except Exception:  # pragma: no cover
    readline = None  # graceful degrade on platforms without readline


Mode = str  # "user" or "admin"


@dataclass(frozen=True)
class ArgSpec:
    """
    Declarative argument spec for a command.

    names: tuple of option strings or a single positional name.
           Examples: ('-c', '--count') or ('hostname',)
    kwargs: passed to argparse.ArgumentParser.add_argument(**kwargs)
            Examples: dict(type=int, default=4, help="...").
    """

    names: Tuple[str, ...]
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Command:
    """
    Declarative command definition.

    tokens: the multi-word command name split into tokens.
            Example: ('show','ip','interface','brief')
    mode:   'user' or 'admin' (the prompt context where it is valid)
    help:   one-line help for listing
    args:   list of ArgSpec to build the command's ArgumentParser
    handler: callable(namespace, argv_tail) -> int
    """

    tokens: Tuple[str, ...]
    mode: Mode
    help: str
    args: List[ArgSpec]
    handler: Callable[[argparse.Namespace, List[str]], int]

    # Internal parser cache created on first use
    _parser: argparse.ArgumentParser | None = field(
        default=None, init=False, repr=False
    )

    def build_parser(self) -> argparse.ArgumentParser:
        if self._parser is not None:
            return self._parser
        prog = " ".join(self.tokens)
        p = argparse.ArgumentParser(prog=prog, add_help=True)
        for spec in self.args:
            p.add_argument(*spec.names, **spec.kwargs)
        self._parser = p
        return p


class CommandRegistry:
    def __init__(self) -> None:
        self._by_mode: Dict[Mode, List[Command]] = {"user": [], "admin": []}

    def register(self, cmd: Command) -> None:
        if cmd.mode not in self._by_mode:
            raise ValueError(f"Unknown mode {cmd.mode}")
        # Basic duplicate guard on identical full tokens
        exists = any(c.tokens == cmd.tokens for c in self._by_mode[cmd.mode])
        if exists:
            raise ValueError(
                f"Duplicate command in mode {cmd.mode}: {' '.join(cmd.tokens)}"
            )
        self._by_mode[cmd.mode].append(cmd)

    def all_tokens(self, mode: Mode) -> List[Tuple[str, ...]]:
        return [c.tokens for c in self._by_mode[mode]]

    def candidates_for_prefix(
        self, mode: Mode, prefix_tokens: Sequence[str]
    ) -> List[Command]:
        """
        Return commands whose token sequence matches the given prefix, token by token,
        allowing each input token to be an unambiguous prefix of the full token.
        """
        out: List[Command] = []
        for c in self._by_mode[mode]:
            if len(prefix_tokens) > len(c.tokens):
                continue
            ok = True
            for i, t in enumerate(prefix_tokens):
                if not c.tokens[i].startswith(t):
                    ok = False
                    break
            if ok:
                out.append(c)
        return out

    def resolve_command(
        self, mode: Mode, input_tokens: Sequence[str]
    ) -> Tuple[Command, List[str]]:
        """
        Resolve input into a specific Command and return (command, argv_tail).
        Abbreviation logic:
          - Grow tokens until a unique command is identified or ambiguity detected.
          - If exact prefix matches multiple commands, raise with suggestions.
        """
        if not input_tokens:
            raise ValueError("empty input")

        # Greedy longest prefix resolution
        for cut in range(len(input_tokens), 0, -1):
            head = input_tokens[:cut]
            tail = input_tokens[cut:]
            matches = self.candidates_for_prefix(mode, head)
            if len(matches) == 1 and (len(head) == len(matches[0].tokens)):
                # Full command matched; remaining tokens are argv
                return matches[0], tail
            elif len(matches) == 1 and len(head) < len(matches[0].tokens):
                # Input ended before completing the command tokens
                needed = " ".join(matches[0].tokens)
                got = " ".join(head)
                raise ValueError(f'incomplete command: "{got}" → expected "{needed}"')
            elif len(matches) > 1:
                # Ambiguity at this head; keep checking shorter heads
                continue

        # If here, either ambiguous or no match
        matches = self.candidates_for_prefix(mode, input_tokens)
        if not matches:
            raise ValueError(f'unknown command: "{" ".join(input_tokens)}"')

        # Ambiguous
        alts = ", ".join(" ".join(c.tokens) for c in matches[:10])
        if len(matches) > 10:
            alts += ", ..."
        raise ValueError(f"ambiguous command: could be {alts}")


class Shell:
    def __init__(self, registry: CommandRegistry) -> None:
        self.registry = registry
        self.mode: Mode = "user"

        if readline:
            self._install_completion()

    # ---- Completion -------------------------------------------------------

    def _install_completion(self) -> None:
        def completer(text: str, state: int) -> str | None:
            # Buffer and cursor position
            buf = readline.get_line_buffer()  # type: ignore[attr-defined]
            try:
                tokens = shlex.split(buf)
            except ValueError:
                tokens = buf.split()  # fallback on unmatched quote

            # Determine which token index is being completed
            # If ends with space, we are starting a new token
            at_new_token = buf.endswith(" ")

            if at_new_token:
                tokens.append("")  # placeholder for the new token

            # If no tokens yet, suggest first token options
            if not tokens:
                opts = sorted(set(t[0] for t in self.registry.all_tokens(self.mode)))
                matches = [o for o in opts if o.startswith(text)]
                return matches[state] if state < len(matches) else None

            # If still within command token sequence, complete by command tokens
            # Find candidates by already-typed prefix tokens
            # We generate completions for the current position.
            cur_index = len(tokens) - 1
            prefix_tokens = tokens[:cur_index]  # tokens before the one being completed
            partial = tokens[cur_index]

            candidates = self.registry.candidates_for_prefix(self.mode, prefix_tokens)
            # Restrict to those where the next token exists and startswith(partial)
            next_tokens = []
            for c in candidates:
                if len(prefix_tokens) < len(c.tokens):
                    nxt = c.tokens[len(prefix_tokens)]
                    if nxt.startswith(partial):
                        next_tokens.append(nxt)

            # If the command name is fully matched, offer option names from ArgSpec
            fully_matched = [
                c for c in candidates if len(prefix_tokens) == len(c.tokens)
            ]
            if fully_matched:
                c = fully_matched[
                    0
                ]  # if multiple, they share same options by design here
                # collect option strings that start with partial
                options = []
                for spec in c.args:
                    for nm in spec.names:
                        if nm.startswith("-") and nm.startswith(partial):
                            options.append(nm)
                next_tokens.extend(options)

            # Deduplicate, sort
            options = sorted(set(next_tokens))
            return options[state] if state < len(options) else None

        readline.set_completer_delims(" \t\n")  # type: ignore[attr-defined]
        readline.parse_and_bind("tab: complete")  # type: ignore[attr-defined]
        readline.set_completer(completer)  # type: ignore[attr-defined]

    # ---- Loop -------------------------------------------------------------

    def prompt(self) -> str:
        return "cli# " if self.mode == "admin" else "cli> "

    def set_mode(self, mode: Mode) -> None:
        if mode not in ("user", "admin"):
            raise ValueError("invalid mode")
        self.mode = mode

    def run(self) -> int:
        while True:
            try:
                line = input(self.prompt())
            except EOFError:
                print()  # newline on Ctrl-D
                return 0
            except KeyboardInterrupt:
                print()  # newline on Ctrl-C
                continue

            line = line.strip()
            if not line:
                continue

            if line in ("quit", "exit") and self.mode == "user":
                return 0

            # Tokenize
            try:
                tokens = shlex.split(line)
            except ValueError as e:
                print(f"parse error: {e}")
                continue

            # Resolve command
            try:
                cmd, argv_tail = self.registry.resolve_command(self.mode, tokens)
            except ValueError as e:
                print(e)
                continue

            # Parse args with the command's parser
            try:
                ns = cmd.build_parser().parse_args(argv_tail)
            except SystemExit:
                # argparse already printed the error/help
                continue
            except Exception as e:
                print(f"argument parsing error: {e}")
                continue

            # Execute
            try:
                rc = cmd.handler(ns, argv_tail)
            except Exception as e:
                print(f"handler error: {e}")
                rc = 1

            if rc is not None and rc != 0:
                # Nonzero codes are printed for visibility
                print(f"(rc={rc})")


# ---- Demo handlers --------------------------------------------------------


def h_help_factory(
    registry: CommandRegistry,
) -> Callable[[argparse.Namespace, List[str]], int]:
    def _h(ns: argparse.Namespace, argv_tail: List[str]) -> int:
        print(f"Mode: {ns.mode}")
        cmds = sorted(registry._by_mode[ns.mode], key=lambda c: c.tokens)
        for c in cmds:
            print(f"  {' '.join(c.tokens):<30} {c.help}")
        return 0

    return _h


def h_enable(shell: Shell) -> Callable[[argparse.Namespace, List[str]], int]:
    def _h(ns: argparse.Namespace, argv_tail: List[str]) -> int:
        shell.set_mode("admin")
        return 0

    return _h


def h_disable(shell: Shell) -> Callable[[argparse.Namespace, List[str]], int]:
    def _h(ns: argparse.Namespace, argv_tail: List[str]) -> int:
        shell.set_mode("user")
        return 0

    return _h


def h_show_ip_interface_brief(ns: argparse.Namespace, argv_tail: List[str]) -> int:
    # Stateless demo output
    print("Interface       IP-Address      OK? Method Status       Protocol")
    print("Ethernet0       192.0.2.10      YES manual up           up")
    print("Ethernet1       unassigned      YES unset  administratively down down")
    return 0


def h_ping(ns: argparse.Namespace, argv_tail: List[str]) -> int:
    # Demo: print intent only. Wire actual ping later.
    host = ns.host
    count = ns.count
    print(f"[demo] would ping {host} count={count}")
    return 0


def h_traceroute(ns: argparse.Namespace, argv_tail: List[str]) -> int:
    host = ns.host
    print(f"[demo] would traceroute to {host}")
    return 0


def h_set_ip_address(ns: argparse.Namespace, argv_tail: List[str]) -> int:
    print(f"[demo] would set {ns.iface} to {ns.address}/{ns.prefix}")
    return 0


# ---- Wiring ---------------------------------------------------------------


def build_registry(shell: Shell) -> CommandRegistry:
    reg = CommandRegistry()

    # help (user)
    reg.register(
        Command(
            tokens=("help",),
            mode="user",
            help="Show commands in current mode",
            args=[
                ArgSpec(
                    ("mode",),
                    dict(choices=("user", "admin"), nargs="?", default="user"),
                )
            ],
            handler=h_help_factory(reg),
        )
    )

    # help (admin)
    reg.register(
        Command(
            tokens=("help",),
            mode="admin",
            help="Show commands in current mode",
            args=[
                ArgSpec(
                    ("mode",),
                    dict(choices=("user", "admin"), nargs="?", default="admin"),
                )
            ],
            handler=h_help_factory(reg),
        )
    )

    # privilege transitions
    reg.register(
        Command(
            tokens=("enable",),
            mode="user",
            help="Enter admin mode",
            args=[],
            handler=h_enable(shell),
        )
    )
    reg.register(
        Command(
            tokens=("disable",),
            mode="admin",
            help="Return to user mode",
            args=[],
            handler=h_disable(shell),
        )
    )
    reg.register(
        Command(  # IOS muscle memory
            tokens=("exit",),
            mode="admin",
            help="Return to user mode",
            args=[],
            handler=h_disable(shell),
        )
    )

    # user-mode operational commands
    reg.register(
        Command(
            tokens=("show", "ip", "interface", "brief"),
            mode="user",
            help="Display IP interfaces summary",
            args=[],
            handler=h_show_ip_interface_brief,
        )
    )
    reg.register(
        Command(
            tokens=("ping",),
            mode="user",
            help="Send ICMP echo requests",
            args=[
                ArgSpec(("host",), dict(help="Hostname or IP")),
                ArgSpec(
                    ("-c", "--count"),
                    dict(type=int, default=4, help="Number of probes"),
                ),
            ],
            handler=h_ping,
        )
    )
    reg.register(
        Command(
            tokens=("traceroute",),
            mode="user",
            help="Trace route to host",
            args=[ArgSpec(("host",), dict(help="Hostname or IP"))],
            handler=h_traceroute,
        )
    )

    # admin-mode config command
    reg.register(
        Command(
            tokens=("set", "ip", "address"),
            mode="admin",
            help="Configure interface IP/prefix",
            args=[
                ArgSpec(("iface",), dict(help="Interface name, e.g., Ethernet0")),
                ArgSpec(("address",), dict(help="IPv4 address, e.g., 192.0.2.10")),
                ArgSpec(("prefix",), dict(type=int, help="Prefix length, e.g., 24")),
            ],
            handler=h_set_ip_address,
        )
    )

    return reg


def main(argv: List[str] | None = None) -> int:
    banner = textwrap.dedent(
        """\
        Cisco-like CLI. Two modes: user (cli>) and admin (cli#).
        Examples:
          help
          show ip interface brief
          ping example.com -c 2
          enable
          set ip address Ethernet0 192.0.2.99 24
          disable
          exit  # from user mode ends the shell
        """
    )
    print(banner)
    dummy_shell = Shell(
        CommandRegistry()
    )  # temporary to satisfy handlers that close over shell
    registry = build_registry(dummy_shell)
    shell = Shell(registry)
    # rebind the enable/disable handlers to real shell if needed
    # (handlers already close over 'shell' created later; we ensured order above)
    return shell.run()


if __name__ == "__main__":
    sys.exit(main())
