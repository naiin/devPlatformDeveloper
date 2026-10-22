#!/usr/bin/env python3
"""Terraform's VirtualBox lifecycle adapter. Operates only on marked lab VMs."""
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

cfg = json.loads(os.environ["INPUT_JSON"])
root = Path(cfg["root"])
runtime = root / ".runtime"
runtime.mkdir(mode=0o700, exist_ok=True)
interface_file = runtime / "hostonly-interface"
marker = "devPlatform/managed-by"


def vbox(*args, check=True):
    result = subprocess.run(["VBoxManage", *map(str, args)], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    if check and result.returncode:
        raise RuntimeError(f"VBoxManage {' '.join(map(str, args))}: {result.stderr.strip()}")
    return result


def interface():
    name = interface_file.read_text().strip()
    if not re.fullmatch(r"vboxnet\d+", name):
        raise RuntimeError("Invalid managed interface record")
    return name


def owned_vm(name):
    info = vbox("showvminfo", name, "--machinereadable", check=False)
    if info.returncode:
        return None
    owner = vbox("getextradata", name, marker).stdout.strip()
    if owner != f"Value: {root}":
        raise RuntimeError(f"Refusing to alter unowned VM {name}")
    return info.stdout


def network_create():
    if interface_file.exists():
        name = interface()
        if f"Name:            {name}\n" in vbox("list", "hostonlyifs").stdout:
            print(f"Using managed interface {name}", flush=True)
            return
    # Abort rather than introducing a route over another active subnet.
    routes = subprocess.check_output(["ip", "-j", "route"], text=True)
    if any(r.get("dst") == f"{cfg['prefix']}.0/24" for r in json.loads(routes)):
        raise RuntimeError("The selected host-only subnet is already routed; choose another network_prefix")
    result = vbox("hostonlyif", "create")
    match = re.search(r"Interface '(vboxnet\d+)' was successfully created", result.stdout)
    if not match:
        raise RuntimeError(f"Cannot identify newly created interface: {result.stdout}")
    name = match.group(1)
    interface_file.write_text(name + "\n")
    vbox("hostonlyif", "ipconfig", name, "--ip", f"{cfg['prefix']}.1", "--netmask", "255.255.255.0")
    vbox("dhcpserver", "add", f"--interface={name}",
         f"--server-ip={cfg['prefix']}.2", "--netmask=255.255.255.0",
         f"--lower-ip={cfg['prefix']}.10", f"--upper-ip={cfg['prefix']}.99", "--enable")
    # Host-only DHCP must not install a default route or a DNS server.
    vbox("dhcpserver", "modify", f"--interface={name}", "--global",
         "--suppress-opt=3", "--suppress-opt=6")
    # The DHCP process loads reservations when it starts. Install every
    # reservation before starting any VM, rather than adding them piecemeal.
    for suffix in range(10, 14):
        vbox("dhcpserver", "modify", f"--interface={name}",
             f"--mac-address=0800275700{suffix}", f"--fixed-address={cfg['prefix']}.{suffix}")
    print(f"Created {name}: {cfg['prefix']}.0/24", flush=True)


def network_delete():
    if interface_file.exists():
        name = interface()
        vbox("dhcpserver", "remove", f"--interface={name}", check=False)
        vbox("hostonlyif", "remove", name)
        interface_file.unlink()


def create():
    name = cfg["name"]
    info = owned_vm(name)
    if info is None:
        vbox("createvm", "--name", name, "--ostype", "Linux_64",
             "--basefolder", root / "vms", "--register")
        vbox("setextradata", name, marker, root)
        info = owned_vm(name)
    if 'VMState="running"' not in info:
        vbox("modifyvm", name, "--memory", cfg["memory"], "--cpus", cfg["cpus"],
             "--ioapic", "on", "--firmware", "efi", "--graphicscontroller", "vmsvga",
             "--vram", "16", "--audio-enabled", "off", "--usb-ohci", "off",
             "--usb-ehci", "off", "--boot1", "disk", "--boot2", "dvd",
             "--boot3", "none", "--boot4", "none", "--nic1", "hostonly",
             "--host-only-adapter1", interface(), "--nic-type1", "virtio",
             "--mac-address1", cfg["mac"], "--cable-connected1", "on",
             "--nic-promisc1", "allow-all", "--nic2", "bridged", "--nic-type2", "82540EM",
             "--bridge-adapter2", cfg["bridge_interface"], "--cable-connected2", "on",
             "--uart1", "0x3F8", "4", "--uart-mode1", "file", runtime / f"{name}-serial.log")
        if 'storagecontrollername0="SATA"' not in info:
            vbox("storagectl", name, "--name", "SATA", "--add", "sata",
                 "--controller", "IntelAhci", "--portcount", "2", "--hostiocache", "on")
        disk = root / "vms" / name / "system.vdi"
        if not disk.exists():
            vbox("createmedium", "disk", "--filename", disk, "--size", cfg["disk_size"], "--format", "VDI")
        vbox("storageattach", name, "--storagectl", "SATA", "--port", "0",
             "--device", "0", "--type", "hdd", "--medium", disk)
        vbox("storageattach", name, "--storagectl", "SATA", "--port", "1",
             "--device", "0", "--type", "dvddrive", "--medium",
             root / ".cache" / cfg["talos_version"] / "metal-amd64.iso")
        vbox("dhcpserver", "modify", f"--interface={interface()}",
             f"--mac-address={cfg['mac']}", f"--fixed-address={cfg['ip']}")
        print(f"Starting {name}: {cfg['ip']}, {cfg['cpus']} CPUs, {cfg['memory']} MiB", flush=True)
        vbox("startvm", name, "--type", "headless")


def delete():
    name = cfg["name"]
    info = owned_vm(name)
    if info is None:
        return
    if 'VMState="running"' in info or 'VMState="paused"' in info:
        vbox("controlvm", name, "poweroff")
    vbox("unregistervm", name, "--delete")
    if interface_file.exists():
        vbox("dhcpserver", "modify", f"--interface={interface()}",
             f"--mac-address={cfg['mac']}", "--remove-config", check=False)


def uplink():
    name = cfg["name"]
    info = owned_vm(name)
    if info is None:
        raise RuntimeError(f"Missing VM {name}")
    adapter = cfg["bridge_interface"]
    if 'nic2="bridged"' in info and f'bridgeadapter2="{adapter}"' in info:
        print(f"{name}: bridged uplink already uses {adapter}", flush=True)
        return
    if 'VMState="running"' in info:
        vbox("controlvm", name, "setlinkstate2", "off")
        vbox("controlvm", name, "nic2", "bridged", adapter)
        vbox("controlvm", name, "setlinkstate2", "on")
    else:
        vbox("modifyvm", name, "--nic2", "bridged", "--bridge-adapter2", adapter)
    print(f"{name}: configured bridged uplink {adapter}", flush=True)


def wait_api():
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((cfg["ip"], 50000), timeout=2):
                print(f"{cfg['name']}: Talos API is reachable at {cfg['ip']}:50000", flush=True)
                return
        except OSError:
            time.sleep(3)
    raise RuntimeError(f"Talos API did not become reachable: inspect {runtime / (cfg['name'] + '-serial.log')}")


if __name__ == "__main__":
    action = sys.argv[1]
    with (runtime / "vbox.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        {"network-create": network_create, "network-delete": network_delete,
         "create": create, "delete": delete, "uplink": uplink}[action]()
    if action == "create":
        wait_api()

