#!/usr/bin/env python3
# Windows 11 interactive CLI with EXEC/CONFIG modes and staged commit.
# Built-ins only. Elevation via PowerShell Start-Process -Verb RunAs.
import argparse
import ctypes
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

APP = "Router"


def is_windows() -> bool:
    return sys.platform == "win32"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def psq(s: str) -> str:
    # PowerShell single-quoted literal
    return "'" + s.replace("'", "''") + "'"


def run_powershell(ps_code: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_code],
        text=True,
        capture_output=True,
        check=check,
    )


def show_ip_interface():
    ps = (
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Select-Object InterfaceAlias,IPAddress,PrefixLength | "
        "Sort-Object InterfaceAlias,IPAddress | "
        "Format-Table -AutoSize"
    )
    proc = run_powershell(ps)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)


def cmd_ping(host: str):
    try:
        subprocess.run(["ping", host], check=False)
    except FileNotFoundError:
        print("ping not found")


def cmd_tracert(host: str):
    try:
        subprocess.run(["tracert", host], check=False)
    except FileNotFoundError:
        print("tracert not found")


def start_elevated_and_apply(plan_path: Path) -> int:
    arglist = ", ".join(
        [psq(sys.executable), psq(__file__), psq("--apply"), psq(str(plan_path))]
    )
    ps = f"Start-Process -FilePath {psq(sys.executable)} -ArgumentList {arglist} -Verb RunAs -Wait -WindowStyle Hidden"
    print("Requesting elevation...")
    rc = subprocess.run(["powershell", "-NoProfile", "-Command", ps]).returncode
    return rc


def apply_plan(plan_path: Path) -> int:
    # Elevated worker. Apply staged operations idempotently.
    try:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to read plan: {e}", file=sys.stderr)
        return 2

    for op in plan.get("ops", []):
        kind = op.get("kind")
        iface = op.get("interface")
        if not iface:
            print("Missing interface in op", file=sys.stderr)
            return 3

        if kind == "clear_ipv4":
            ps = (
                f"Get-NetIPAddress -InterfaceAlias {psq(iface)} -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
                "Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue"
            )
            proc = run_powershell(ps)
            if proc.returncode != 0:
                print(proc.stderr, file=sys.stderr)

        elif kind == "set_ipv4":
            ip = op["ip"]
            prefix = int(op["prefix"])
            gw = op.get("gateway")
            add_gw = "" if not gw else f"-DefaultGateway {psq(gw)} "
            ps = (
                f"New-NetIPAddress -InterfaceAlias {psq(iface)} -IPAddress {psq(ip)} "
                f"-PrefixLength {prefix} {add_gw}-PolicyStore ActiveStore -ErrorAction Stop"
            )
            proc = run_powershell(ps)
            if proc.returncode != 0:
                print(proc.stderr, file=sys.stderr)
                return proc.returncode

        elif kind == "set_dns":
            servers = op.get("dns", [])
            arr = "@(" + ", ".join(psq(s) for s in servers) + ")"
            ps = f"Set-DnsClientServerAddress -InterfaceAlias {psq(iface)} -ServerAddresses {arr} -ErrorAction Stop"
            proc = run_powershell(ps)
            if proc.returncode != 0:
                print(proc.stderr, file=sys.stderr)
                return proc.returncode

        elif kind == "replace_ipv4":
            # convenience composite: clear then set
            ip = op["ip"]
            prefix = int(op["prefix"])
            gw = op.get("gateway")
            ps_clear = (
                f"Get-NetIPAddress -InterfaceAlias {psq(iface)} -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
                "Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue"
            )
            run_powershell(ps_clear)
            add_gw = "" if not gw else f"-DefaultGateway {psq(gw)} "
            ps_set = (
                f"New-NetIPAddress -InterfaceAlias {psq(iface)} -IPAddress {psq(ip)} "
                f"-PrefixLength {prefix} {add_gw}-PolicyStore ActiveStore -ErrorAction Stop"
            )
            proc = run_powershell(ps_set)
            if proc.returncode != 0:
                print(proc.stderr, file=sys.stderr)
                return proc.returncode
        else:
            print(f"Unknown op: {kind}", file=sys.stderr)
            return 4

    print("Applied plan successfully.")
    return 0


class CLI:
    def __init__(self):
        self.mode = "exec"  # exec | config | config-if
        self.iface = None  # current interface alias in config-if
        self.candidate = {"ops": []}  # staged ops

    # Prompt strings
    def prompt(self) -> str:
        if self.mode == "exec":
            return f"{APP}> "
        if self.mode == "config":
            return f"{APP}(config)# "
        if self.mode == "config-if":
            return f"{APP}(config-if {self.iface})# "
        return "> "

    # Parsing helpers
    def loop(self):
        while True:
            try:
                line = input(self.prompt()).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if not self.dispatch(line):
                break

    def dispatch(self, line: str) -> bool:
        toks = line.split()
        cmd = toks[0].lower()

        # Universal
        if cmd in ("quit", "exit") and self.mode == "exec":
            return False
        if cmd == "end":
            self.mode = "exec"
            self.iface = None
            return True
        if cmd in ("?", "help"):
            self.help()
            return True

        # EXEC mode
        if self.mode == "exec":
            if (
                cmd == "show"
                and len(toks) >= 2
                and toks[1] == "ip"
                and (len(toks) == 3 and toks[2] == "interface")
            ):
                show_ip_interface()
                return True
            if cmd == "ping" and len(toks) >= 2:
                cmd_ping(toks[1])
                return True
            if cmd in ("tracert", "traceroute") and len(toks) >= 2:
                cmd_tracert(toks[1])
                return True
            if cmd == "configure" and len(toks) >= 2 and toks[1] == "terminal":
                self.mode = "config"
                return True
            print("Unknown EXEC command.")
            return True

        # CONFIG mode
        if self.mode == "config":
            if cmd == "interface" and len(toks) >= 2:
                self.iface = " ".join(toks[1:])
                self.mode = "config-if"
                return True
            if cmd == "commit":
                self.commit_candidate()
                return True
            if cmd in ("no", "discard") and (len(toks) == 2 and toks[1] == "candidate"):
                self.candidate = {"ops": []}
                print("Candidate discarded.")
                return True
            if cmd == "show" and len(toks) == 2 and toks[1] == "candidate":
                print(json.dumps(self.candidate, indent=2))
                return True
            if cmd in ("exit",):
                self.mode = "exec"
                return True
            print("Unknown CONFIG command.")
            return True

        # CONFIG-IF mode
        if self.mode == "config-if":
            if cmd == "ip" and len(toks) >= 2 and toks[1] == "address":
                # ip address <ADDR> <PREFIX> [GATEWAY]
                if len(toks) < 4:
                    print("Usage: ip address <ADDR> <PREFIX> [GATEWAY]")
                    return True
                addr = toks[2]
                prefix = toks[3]
                gw = toks[4] if len(toks) >= 5 else None
                # Stage a replace: clear then set new
                self.candidate["ops"].append(
                    {
                        "kind": "replace_ipv4",
                        "interface": self.iface,
                        "ip": addr,
                        "prefix": int(prefix),
                        "gateway": gw,
                    }
                )
                print(
                    f"Staged replace IPv4 on {self.iface}: {addr}/{prefix}"
                    + (f" gw {gw}" if gw else "")
                )
                return True
            if cmd == "dns" and len(toks) >= 2:
                servers = toks[1:]
                self.candidate["ops"].append(
                    {"kind": "set_dns", "interface": self.iface, "dns": servers}
                )
                print(f"Staged DNS on {self.iface}: {' '.join(servers)}")
                return True
            if (
                cmd == "no"
                and len(toks) == 3
                and toks[1] == "ip"
                and toks[2] == "address"
            ):
                self.candidate["ops"].append(
                    {"kind": "clear_ipv4", "interface": self.iface}
                )
                print(f"Staged clear IPv4 on {self.iface}")
                return True
            if cmd in ("exit",):
                self.mode = "config"
                self.iface = None
                return True
            print("Unknown CONFIG-IF command.")
            return True

        return True

    def commit_candidate(self):
        if not self.candidate["ops"]:
            print("Nothing to commit.")
            return
        # Write plan
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
            json.dump(self.candidate, tf)
            tf_path = Path(tf.name)
        # Launch elevated child to apply and wait
        rc = start_elevated_and_apply(tf_path)
        try:
            tf_path.unlink(missing_ok=True)
        except Exception:
            pass
        if rc == 0:
            print("Commit complete.")
            self.candidate = {"ops": []}
        else:
            print(f"Commit failed with code {rc}.")

    def help(self):
        help_text = """
        Available commands:
        - config: Enter configuration mode
        - show: Show current configuration
        - exit: Exit configuration mode
        - ip address <ADDR> <PREFIX> [GATEWAY]: Configure IP address
        - no ip address: Remove IP address
        - dns <SERVER1> <SERVER2> ...: Configure DNS servers
        - help: Show this help text
        """
        print(help_text)


def main():
    if not is_windows():
        print("Windows-only.", file=sys.stderr)
        sys.exit(1)

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--apply", help="internal: path to plan.json for elevated apply")
    args, _ = ap.parse_known_args()

    if args.apply:
        if not is_admin():
            print("Apply requires elevation.", file=sys.stderr)
            sys.exit(1)
        sys.exit(apply_plan(Path(args.apply)))

    print(f"{APP} interactive CLI. Type 'help'. Ctrl+C to quit.")
    cli = CLI()
    cli.loop()


if __name__ == "__main__":
    main()
