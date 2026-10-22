#!/usr/bin/env python3
"""Inspect and explicitly reconcile Argo CD Applications using Kubernetes auth."""
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
KUBECTL = ROOT / "scripts/kubectl"


def kubectl(*args, data=None):
    return subprocess.check_output([str(KUBECTL), *args], input=data, text=True)


def app(name):
    return json.loads(kubectl("-n", "argocd", "get", "application", name, "-o", "json"))


def wait(name, revision=None, timeout=600):
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        obj = app(name)
        status = obj.get("status", {})
        summary = (status.get("sync", {}).get("status"), status.get("health", {}).get("status"),
                   status.get("operationState", {}).get("phase"), status.get("sync", {}).get("revision"))
        if summary != previous:
            print(f"{name}: sync={summary[0]}, health={summary[1]}, operation={summary[2]}, revision={summary[3]}", flush=True)
            previous = summary
        if summary[0] == "Synced" and summary[1] == "Healthy" and summary[2] != "Running" and (not revision or summary[3] == revision):
            return obj
        conditions = status.get("conditions", [])
        errors = [c for c in conditions if c.get("type", "").endswith("Error")]
        if errors:
            print(json.dumps(errors), flush=True)
        time.sleep(3)
    raise RuntimeError(f"Timed out waiting for {name}: {previous}")


def sync(name):
    # Pin the explicit operation to the revision reviewed by Argo, never an
    # unbounded moving branch during the production sync operation.
    obj = app(name)
    revision = obj.get("status", {}).get("sync", {}).get("revision")
    if not revision:
        raise RuntimeError("Argo has not resolved a Git revision yet; refresh and retry")
    patch = {"operation": {"initiatedBy": {"username": "devplatform-explicit-sync"},
                           "sync": {"revision": revision, "prune": True,
                                    "syncOptions": ["CreateNamespace=true", "ApplyOutOfSyncOnly=true"]}}}
    print(kubectl("-n", "argocd", "patch", "application", name, "--type=merge", "-p", json.dumps(patch)), end="")
    wait(name, revision)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "wait", "sync", "refresh"])
    parser.add_argument("application", nargs="?")
    parser.add_argument("--revision")
    args = parser.parse_args()
    if args.command == "status":
        print(kubectl("-n", "argocd", "get", "applications,applicationsets"), end="")
    else:
        if not args.application:
            parser.error("application name is required")
        if args.command == "wait":
            wait(args.application, args.revision)
        elif args.command == "sync":
            sync(args.application)
        else:
            print(kubectl("-n", "argocd", "annotate", "application", args.application,
                          "argocd.argoproj.io/refresh=hard", "--overwrite"), end="")

