#!/usr/bin/env python3
"""
win-router-cli.py

Single-file interactive CLI for Windows 11 that accepts Cisco-like
commands and maps them to Windows networking commands when possible.

Requirements:
 - Python 3.9+
 - Run as Administrator for commands that change system state.

Usage:
 python win-router-cli.py [--config CONFIGFILE]
"""

import argparse
import ctypes
import logging
import shlex
import subprocess
import sys
from pathlib import Path

PROMPT = "Router> "
CONF_PROMPT = "Router(config)# "

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("win-router-cli")


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_cmd(cmd, capture=False):
    """Run shell command. Return (rc, stdout, stderr)."""
    if isinstance(cmd, str):
        cmd = cmd
    # Use shell for Windows builtins like 'route' and 'arp'
    proc = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
    out = proc.stdout if capture else None
    err = proc.stderr if capture else None
    return proc.returncode, out, err


class RouterCLI:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.running_config = {"interfaces": {}, "static_routes": []}
        self.in_config_mode = False
        self.current_iface = None
        self._load_config()

    def _load_config(self):
        if self.config_path and self.config_path.exists():
            try:
                text = self.config_path.read_text()
                # very small and simple loader: each line "interface NAME ip A.B.C.D MASK"
                for ln in text.splitlines():
                    ln = ln.strip()
                    if not ln or ln.startswith("#"):
                        continue
                    parts = ln.split()
                    if parts[0] == "interface" and len(parts) >= 2:
                        name = parts[1]
                        self.running_config["interfaces"].setdefault(name, {})
                        if "ip" in parts:
                            i = parts.index("ip")
                            self.running_config["interfaces"][name]["ip"] = parts[i + 1]
                            self.running_config["interfaces"][name]["mask"] = parts[i + 2]
                    if parts[0] == "route" and len(parts) >= 4:
                        self.running_config["static_routes"].append(parts[1:4])
                logger.info(f"Loaded config from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")

    def _write_config_file(self, path: Path):
        lines = []
        for ifname, data in self.running_config["interfaces"].items():
            ip = data.get("ip")
            mask = data.get("mask")
            if ip and mask:
                lines.append(f"interface {ifname} ip {ip} {mask}")
            else:
                lines.append(f"interface {ifname}")
        for r in self.running_config["static_routes"]:
            lines.append("route " + " ".join(r))
        path.write_text("\n".join(lines))
        logger.info(f"Wrote config to {path}")

    def do_show(self, args: str):
        tokens = args.split()
        if not tokens:
            logger.info("Available show: ip interface brief | running-config | arp | route")
            return
        if tokens[0] == "ip" and tokens[1:] == ["interface", "brief"]:
            rc, out, _ = run_cmd("netsh interface ip show addresses", capture=True)
            if rc == 0:
                logger.info(out)
            else:
                rc2, out2, _ = run_cmd("ipconfig /all", capture=True)
                logger.info(out2)
            return
        if tokens[0] == "running-config":
            self.show_running_config()
            return
        if tokens[0] == "arp":
            rc, out, _ = run_cmd("arp -a", capture=True)
            logger.info(out)
            return
        if tokens[0] == "route":
            rc, out, _ = run_cmd("route print", capture=True)
            logger.info(out)
            return
        logger.info("Unknown show command")

    def show_running_config(self):
        out_lines = []
        for ifname, data in self.running_config["interfaces"].items():
            out_lines.append(f"interface {ifname}")
            if "ip" in data:
                out_lines.append(f"  ip address {data['ip']} {data['mask']}")
            if data.get("shutdown"):
                out_lines.append("  shutdown")
        for r in self.running_config["static_routes"]:
            out_lines.append("route " + " ".join(r))
        logger.info("\n".join(out_lines) if out_lines else "No running configuration")

    def cmd_configure(self, args: str):
        if args.strip() == "terminal":
            self.in_config_mode = True
            logger.info("Enter configuration mode. Type 'exit' to return.")
            return
        logger.info("Usage: configure terminal")

    def config_interface(self, iface: str, subcmd: str):
        tokens = shlex.split(subcmd)
        if not tokens:
            logger.info("interface configuration mode. Supported: ip address, shutdown, no shutdown, exit")
            return
        if tokens[0] == "ip" and tokens[1] == "address" and len(tokens) >= 4:
            ip = tokens[2]
            mask = tokens[3]
            self.running_config["interfaces"].setdefault(iface, {})["ip"] = ip
            self.running_config["interfaces"][iface]["mask"] = mask
            logger.info(f"Set {iface} IP {ip} {mask} in running-config")
            # apply to Windows using netsh (requires admin)
            if is_admin():
                # Attempt to set static IP with netsh. This will fail for interfaces with different names.
                cmd = f'netsh interface ip set address name="{iface}" static {ip} {mask}'
                rc, _, err = run_cmd(cmd, capture=True)
                if rc != 0:
                    logger.warning(f"netsh failed: {err}")
                else:
                    logger.info("Applied to system via netsh")
            else:
                logger.info("Not admin: skipping system apply")
            return
        if tokens[0] == "shutdown":
            self.running_config["interfaces"].setdefault(iface, {})["shutdown"] = True
            if is_admin():
                cmd = f'netsh interface set interface "{iface}" admin=disabled'
                rc, _, err = run_cmd(cmd, capture=True)
                if rc != 0:
                    logger.warning(f"netsh failed: {err}")
                else:
                    logger.info("Interface administratively down")
            else:
                logger.info("Not admin: simulated shutdown in running-config")
            return
        if tokens[0] == "no" and tokens[1] == "shutdown":
            self.running_config["interfaces"].setdefault(iface, {})["shutdown"] = False
            if is_admin():
                cmd = f'netsh interface set interface "{iface}" admin=enabled'
                rc, _, err = run_cmd(cmd, capture=True)
                if rc != 0:
                    logger.warning(f"netsh failed: {err}")
                else:
                    logger.info("Interface administratively up")
            else:
                logger.info("Not admin: simulated no shutdown in running-config")
            return
        logger.info("Unknown interface command")

    def do_ping(self, args: str):
        if not args:
            logger.info("Usage: ping <destination>")
            return
        cmd = f'ping {args}'
        rc, out, _ = run_cmd(cmd, capture=True)
        logger.info(out)

    def do_traceroute(self, args: str):
        if not args:
            logger.info("Usage: traceroute <host>")
            return
        cmd = f'tracert {args}'
        rc, out, _ = run_cmd(cmd, capture=True)
        logger.info(out)

    def do_route(self, args: str):
        tokens = shlex.split(args)
        if not tokens:
            logger.info("Usage: route add|delete|show ...")
            return
        if tokens[0] == "add" and len(tokens) >= 3:
            dest = tokens[1]
            mask = tokens[2]
            # optional gateway and metric
            gw = tokens[3] if len(tokens) >= 4 else "0.0.0.0"
            cmd = f'route add {dest} mask {mask} {gw}'
            rc, out, err = run_cmd(cmd, capture=True)
            if rc == 0:
                self.running_config["static_routes"].append([dest, mask, gw])
                logger.info(out or "Route added")
            else:
                logger.warning(err)
            return
        if tokens[0] == "delete" and len(tokens) >= 2:
            dest = tokens[1]
            cmd = f'route delete {dest}'
            rc, out, err = run_cmd(cmd, capture=True)
            if rc == 0:
                self.running_config["static_routes"] = [r for r in self.running_config["static_routes"] if r[0] != dest]
                logger.info(out or "Route deleted")
            else:
                logger.warning(err)
            return
        if tokens[0] in ("show", "print"):
            rc, out, _ = run_cmd("route print", capture=True)
            logger.info(out)
            return
        logger.info("Unknown route subcommand")

    def onecmd(self, line: str):
        line = line.strip()
        if not line:
            return
        if self.in_config_mode:
            # config mode parsing
            if line == "exit":
                self.in_config_mode = False
                self.current_iface = None
                logger.info("Exit configuration mode")
                return
            if line.startswith("interface "):
                parts = shlex.split(line)
                if len(parts) >= 2:
                    self.current_iface = parts[1]
                    logger.info(f"Enter interface {self.current_iface} config. Type 'exit' to leave interface.")
                    return
            if self.current_iface:
                if line == "exit":
                    self.current_iface = None
                    logger.info("Exit interface config")
                    return
                # handle interface subcommands
                self.config_interface(self.current_iface, line)
                return
            # other config commands
            if line.startswith("hostname "):
                _, name = line.split(None, 1)
                self.running_config["hostname"] = name
                logger.info(f"Hostname set to {name}")
                return
            if line.startswith("ip route "):
                # format: ip route DEST MASK GW
                parts = shlex.split(line)
                if len(parts) >= 5:
                    dest = parts[2]
                    mask = parts[3]
                    gw = parts[4]
                    self.running_config["static_routes"].append([dest, mask, gw])
                    logger.info("Added ip route to running-config")
                    return
            logger.info("Unknown config command")
            return

        # top-level commands
        if line in ("exit", "quit"):
            logger.info("Exiting.")
            sys.exit(0)
        if line.startswith("show "):
            self.do_show(line[len("show ") :].strip())
            return
        if line.startswith("configure"):
            self.cmd_configure(line[len("configure ") :].strip() if len(line) > 9 else "")
            return
        if line.startswith("ping "):
            self.do_ping(line[len("ping ") :].strip())
            return
        if line.startswith("traceroute "):
            self.do_traceroute(line[len("traceroute ") :].strip())
            return
        if line.startswith("route "):
            self.do_route(line[len("route ") :].strip())
            return
        if line in ("write memory", "copy running-config startup-config", "save"):
            if self.config_path:
                self._write_config_file(self.config_path)
            else:
                logger.info("No config path provided")
            return
        if line == "show version":
            logger.info("win-router-cli v0.1 - mapped to Windows network tools")
            return
        if line == "help" or line == "?":
            self.print_help()
            return
        logger.info("Unknown command. Type 'help' for commands.")

    def print_help(self):
        help_text = (
            "Supported commands: show, configure terminal, ping, traceroute, route, write memory, exit\n"
            "Inside config: interface <name>, ip address <ip> <mask>, shutdown, no shutdown, ip route\n"
            "show options: show ip interface brief | show running-config | show arp | show route"
        )
        logger.info(help_text)

    def cmdloop(self):
        try:
            while True:
                prompt = CONF_PROMPT if self.in_config_mode else PROMPT
                try:
                    line = input(prompt)
                except EOFError:
                    logger.info("")
                    break
                try:
                    self.onecmd(line)
                except SystemExit:
                    raise
                except Exception as e:
                    logger.exception(f"Command error: {e}")
        except KeyboardInterrupt:
            logger.info("\nInterrupted. Exiting.")


def main():
    parser = argparse.ArgumentParser(description="Windows Cisco-like interactive networking CLI")
    parser.add_argument("--config", "-c", type=Path, default=Path.cwd() / "running-config.txt", help="path to save/load config")
    args = parser.parse_args()
    if not is_admin():
        logger.info("Warning: Not running as Administrator. Some commands will be simulated only.")
    cli = RouterCLI(args.config)
    cli.print_help()
    cli.cmdloop()


if __name__ == "__main__":
    main()
