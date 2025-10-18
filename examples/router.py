# router.py
#!/usr/bin/env python3
"""
Windows Cisco-like CLI (per-call PowerShell backend, dual-stack).
Requires: Python 3.9+, Windows 11. Run as Administrator for changes.
Usage: python router.py [-c CONFIGFILE]
"""

import argparse
import ctypes
import json
import logging
import shlex
import subprocess
import sys
from ipaddress import ip_address, ip_network
from pathlib import Path

PROMPT = "Router> "
CONF_PROMPT = "Router(config)# "
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("router")

PS_SCRIPT = str((Path(__file__).parent / "network.ps1").resolve())


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_ps(action: str, payload: dict) -> tuple[int, str, str]:
    cmd = [
        "powershell",
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        PS_SCRIPT,
        "-Action",
        action,
        "-JsonArgs",
        json.dumps(payload),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


# WORKING ON
def mask_to_cidr(mask: str) -> int:
    parts = [int(x) for x in mask.split(".")]
    n = 0
    for p in parts:
        match p:
            case 0 | 128 | 192 | 224 | 240 | 248 | 252 | 254 | 255:
                pass
        if p < 0 or p > 255:
            raise ValueError("invalid mask")
        n += bin(p).count("1")
    return n


def ipv4_prefix(dest: str, mask: str) -> str:
    plen = mask_to_cidr(mask)
    return f"{dest}/{plen}"


def is_ipv6(s: str) -> bool:
    try:
        return ip_address(s).version == 6
    except Exception:
        return ":" in s


class RouterCLI:
    def __init__(self, cfg: Path):
        self.config_path = cfg
        self.in_config = False
        self.iface = None
        self.running = {
            "hostname": "Router",
            "interfaces": {},
            "routes_v4": [],
            "routes_v6": [],
        }
        self._load()

    def _load(self):
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text())
                if isinstance(data, dict):
                    self.running = data
                    log.info(f"Loaded config {self.config_path}")
            except Exception as e:
                log.info(f"Config load failed: {e}")

    def _save(self):
        self.config_path.write_text(json.dumps(self.running, indent=2))
        log.info(f"Saved to {self.config_path}")

    # ---------- show ----------
    def show_ip_int_brief(self, v: str):
        rc, out, err = run_ps("GetInterfaces", {"Version": v})
        if rc != 0:
            log.info(err or "PowerShell error")
            return
        try:
            items = json.loads(out)
        except Exception:
            log.info(out)
            return
        # Cisco-clean: Interface  IP              Status
        lines = []
        for itf in items:
            name = itf.get("Name", "")
            admin = itf.get("AdminStatus", "down")
            oper = itf.get("OperStatus", "down")
            status = "up" if (admin == "Up" and oper == "Up") else "down"
            ips = itf.get("IPv4", []) if v == "IPv4" else itf.get("IPv6", [])
            ip1 = ips[0] if ips else "unassigned"
            lines.append(f"{name:25} {ip1:40} {status}")
        hdr = f"{'Interface':25} {'IP address':40} {'Status'}"
        log.info(hdr + "\n" + "\n".join(lines) if lines else "No interfaces")

    def show_routes(self, v: str):
        rc, out, err = run_ps("GetRoutes", {"Version": v})
        if rc != 0:
            log.info(err or "PowerShell error")
            return
        try:
            routes = json.loads(out)
        except Exception:
            log.info(out)
            return
        hdr = f"{'Prefix':25} {'NextHop':25} {'Iface':20} {'Metric':6}"
        lines = []
        for r in routes:
            lines.append(
                f"{r.get('Destination',''):25} {r.get('NextHop','-'):25} {r.get('InterfaceAlias',''):20} {str(r.get('RouteMetric','')):6}"
            )
        log.info(hdr + "\n" + "\n".join(lines) if lines else "No routes")

    # ---------- exec ----------
    def do_ping(self, target: str):
        if not target:
            log.info("Usage: ping <destination>")
            return
        rc, out, err = run_ps("Ping", {"Target": target, "Count": 4})
        log.info(out if out else err)

    def do_traceroute(self, target: str):
        if not target:
            log.info("Usage: traceroute <destination>")
            return
        # use Windows tracert for familiar output
        proc = subprocess.run(["tracert", target], text=True, capture_output=True)
        log.info(proc.stdout or proc.stderr)

    # ---------- config mode ----------
    def int_set_ip(self, name: str, ip: str, mask_or_plen: str):
        if is_ipv6(ip):
            # expect prefix length for IPv6
            try:
                prefix = f"{ip}/{int(mask_or_plen)}" if "/" not in ip else ip
            except Exception:
                log.info("IPv6 usage: ipv6 address <addr> <prefixlen>")
                return
            payload = {"Name": name, "Version": "IPv6", "Prefix": prefix}
            rc, out, err = run_ps("SetIP", payload)
            log.info(out or err or "OK")
            self.running["interfaces"].setdefault(name, {}).setdefault(
                "ipv6", []
            ).append(prefix)
        else:
            # IPv4 expects dotted mask. Convert to prefix.
            try:
                prefix = ipv4_prefix(ip, mask_or_plen)
            except Exception:
                log.info("IPv4 usage: ip address <addr> <mask>")
                return
            payload = {"Name": name, "Version": "IPv4", "Prefix": prefix}
            rc, out, err = run_ps("SetIP", payload)
            log.info(out or err or "OK")
            self.running["interfaces"].setdefault(name, {}).setdefault(
                "ipv4", []
            ).append(prefix)

    def int_shutdown(self, name: str, down: bool):
        action = "DisableInterface" if down else "EnableInterface"
        rc, out, err = run_ps(action, {"Name": name})
        log.info(out or err or "OK")
        self.running["interfaces"].setdefault(name, {})["admin"] = (
            "down" if down else "up"
        )

    def add_route(
        self, v: str, dest: str, mask_or_plen: str, gw: str, iface: str | None
    ):
        if v == "IPv4":
            prefix = ipv4_prefix(dest, mask_or_plen)
        else:
            prefix = f"{dest}/{mask_or_plen}" if "/" not in dest else dest
        payload = {
            "Version": v,
            "Destination": prefix,
            "NextHop": gw,
            "InterfaceAlias": iface,
        }
        rc, out, err = run_ps("AddRoute", payload)
        log.info(out or err or "OK")
        key = "routes_v4" if v == "IPv4" else "routes_v6"
        self.running[key].append({"prefix": prefix, "gw": gw, "iface": iface or ""})

    # ---------- dispatcher ----------
    def onecmd(self, line: str):
        line = line.strip()
        if not line:
            return
        if self.in_config:
            if line == "exit":
                self.in_config = False
                self.iface = None
                log.info("Exit configuration mode")
                return
            if line.startswith("interface "):
                parts = shlex.split(line)
                if len(parts) >= 2:
                    self.iface = parts[1]
                    log.info(f"Enter interface {self.iface}")
                return
            if self.iface:
                if line.lower().startswith("ip address "):
                    _, _, rest = line.partition("ip address ")
                    parts = shlex.split(rest)
                    if len(parts) >= 2:
                        self.int_set_ip(self.iface, parts[0], parts[1])
                    else:
                        log.info("Usage: ip address <A.B.C.D> <MASK>")
                    return
                if line.lower().startswith("ipv6 address "):
                    _, _, rest = line.partition("ipv6 address ")
                    parts = shlex.split(rest)
                    if len(parts) >= 2:
                        self.int_set_ip(self.iface, parts[0], parts[1])
                    else:
                        log.info("Usage: ipv6 address <ADDR> <PREFIXLEN>")
                    return
                if line == "shutdown":
                    self.int_shutdown(self.iface, True)
                    return
                if line == "no shutdown":
                    self.int_shutdown(self.iface, False)
                    return
                log.info("Unknown interface command")
                return
            if line.lower().startswith("hostname "):
                self.running["hostname"] = line.split(None, 1)[1]
                log.info("OK")
                return
            if line.lower().startswith("ip route "):
                parts = shlex.split(line)[2:]
                if len(parts) >= 3:
                    self.add_route(
                        "IPv4",
                        parts[0],
                        parts[1],
                        parts[2],
                        parts[3] if len(parts) >= 4 else None,
                    )
                else:
                    log.info("Usage: ip route <DEST> <MASK> <GW> [IFACE]")
                return
            if line.lower().startswith("ipv6 route "):
                parts = shlex.split(line)[2:]
                if len(parts) >= 2:
                    dest = parts[0]
                    gw = parts[1]
                    iface = parts[2] if len(parts) >= 3 else None
                    # allow DEST as prefix or (addr plen)
                    if "/" not in dest and len(parts) >= 3:
                        log.info("Usage: ipv6 route <PREFIX> <GW> [IFACE]")
                        return
                    self.add_route("IPv6", dest, "0", gw, iface)  # plen embedded
                else:
                    log.info("Usage: ipv6 route <PREFIX> <GW> [IFACE]")
                return
            log.info("Unknown config command")
            return

        # exec mode
        if line in ("exit", "quit"):
            sys.exit(0)
        if line == "configure terminal":
            self.in_config = True
            log.info("Enter configuration mode")
            return
        if line == "show ip interface brief":
            self.show_ip_int_brief("IPv4")
            return
        if line == "show ipv6 interface brief":
            self.show_ip_int_brief("IPv6")
            return
        if line == "show ip route":
            self.show_routes("IPv4")
            return
        if line == "show ipv6 route":
            self.show_routes("IPv6")
            return
        if line.startswith("ping "):
            self.do_ping(line.split(None, 1)[1])
            return
        if line.startswith("traceroute "):
            self.do_traceroute(line.split(None, 1)[1])
            return
        if line in ("write memory", "copy running-config startup-config", "save"):
            self._save()
            return
        if line == "show running-config":
            log.info(json.dumps(self.running, indent=2))
            return
        if line == "show version":
            log.info("router.py v0.2 (per-call PowerShell, dual-stack)")
            return
        log.info("Unknown command")

    def loop(self):
        if not is_admin():
            log.info("Warning: not Administrator. Changes may fail.")
        while True:
            try:
                prompt = CONF_PROMPT if self.in_config else PROMPT
                line = input(prompt)
            except EOFError:
                break
            except KeyboardInterrupt:
                log.info("")
                break
            else:
                self.onecmd(line)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "-c", "--config", type=Path, default=Path.cwd() / "running-config.json"
    )
    args = p.parse_args()
    RouterCLI(args.config).loop()


if __name__ == "__main__":
    main()
