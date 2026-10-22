#!/usr/bin/env python3
"""Idempotent /etc/hosts update with a backup and a narrowly marked block."""
import argparse
from datetime import datetime
import ipaddress
import os
from pathlib import Path
import re
import shutil

parser = argparse.ArgumentParser()
parser.add_argument("--ip", default="192.168.57.200")
parser.add_argument("--hostname", default="demo.talos.test")
parser.add_argument("--write-instructions", action="store_true")
args = parser.parse_args()
ipaddress.IPv4Address(args.ip)
if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.test", args.hostname):
    parser.error("Expected a local .test hostname")
start, end = "# BEGIN devPlatform Talos lab", "# END devPlatform Talos lab"
block = f"{start}\n{args.ip} {args.hostname}\n{end}\n"
if args.write_instructions:
    generated = Path(__file__).resolve().parent.parent / "generated"
    generated.mkdir(mode=0o700, exist_ok=True)
    (generated / "hosts-entry.txt").write_text(block)
    print(f"Hosts entry ready: {args.ip} {args.hostname}")
else:
    if os.geteuid() != 0:
        parser.error("Run this command with sudo to update /etc/hosts")
    hosts = Path("/etc/hosts")
    original = hosts.read_text()
    cleaned = re.sub(r"(?m)^" + re.escape(start) + r"\n.*?^" + re.escape(end) + r"\n?", "", original, flags=re.S)
    # Preserve unrelated aliases, including aliases that share a line.
    lines = []
    for line in cleaned.splitlines():
        body, sep, comment = line.partition("#")
        parts = body.split()
        if args.hostname in parts[1:]:
            parts = [parts[0]] + [part for part in parts[1:] if part != args.hostname]
            if len(parts) > 1:
                lines.append(" ".join(parts) + (f" #{comment}" if sep else ""))
            elif sep:
                lines.append(f"#{comment}")
        else:
            lines.append(line)
    updated = "\n".join(lines).rstrip() + "\n\n" + block
    if updated != original:
        backup = f"/etc/hosts.talos-backup-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(hosts, backup)
        hosts.write_text(updated)
        print(f"Updated /etc/hosts; backup: {backup}")
    else:
        print("/etc/hosts already configured")

