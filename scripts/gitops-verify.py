#!/usr/bin/env python3
"""Exercise real staging self-healing and production's explicit-sync policy."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from gitops import ROOT, app, kubectl, sync, wait


def resource(kind, name, namespace):
    return json.loads(kubectl("-n", namespace, "get", kind, name, "-o", "json"))


def until(description, predicate, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            print(f"PASS: {description}", flush=True)
            return result
        time.sleep(0.5)
    raise RuntimeError(f"Timed out: {description}")


def run():
    evidence = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": {}}
    for name in ["platform-bootstrap", "staging-hello", "production-hello"]:
        wait(name)

    stage = app("staging-hello")
    prod = app("production-hello")
    assert stage["spec"]["syncPolicy"]["automated"]["selfHeal"] is True
    assert not prod["spec"].get("syncPolicy", {}).get("automated", {}).get("enabled", False)
    intended = resource("configmap", "hello-settings", "staging-hello")["data"]["message"]
    marker = "manual-drift-demonstration-" + str(time.time_ns())
    evidence["staging"] = {"revision": stage["status"]["sync"]["revision"],
                           "desired_message": intended, "manual_message": marker, "samples": []}
    kubectl("-n", "staging-hello", "patch", "configmap", "hello-settings", "--type=merge",
            "-p", json.dumps({"data": {"message": marker}}))
    observed = set()

    def staging_healed():
        state = app("staging-hello")["status"].get("sync", {}).get("status")
        value = resource("configmap", "hello-settings", "staging-hello")["data"]["message"]
        sample = (state, value)
        if sample not in observed:
            evidence["staging"]["samples"].append({"sync": state, "message": value})
            observed.add(sample)
            print(f"staging: {state}, message={value}", flush=True)
        return any(s[0] == "OutOfSync" for s in observed) and value == intended and state == "Synced"

    until("staging drift detected and automatically repaired", staging_healed)
    evidence["checks"]["staging_drift_detected_and_self_healed"] = True

    intended_replicas = resource("deployment", "hello", "production-hello")["spec"]["replicas"]
    manual_replicas = intended_replicas + 1
    evidence["production"] = {"revision": prod["status"]["sync"]["revision"],
                              "desired_replicas": intended_replicas, "manual_replicas": manual_replicas,
                              "hold_seconds": 45}
    kubectl("-n", "production-hello", "scale", "deployment/hello", f"--replicas={manual_replicas}")
    until("production drift detected", lambda: app("production-hello")["status"]["sync"]["status"] == "OutOfSync")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        current = resource("deployment", "hello", "production-hello")["spec"]["replicas"]
        assert current == manual_replicas, f"Production was unexpectedly auto-reconciled: {current}"
        assert app("production-hello")["status"]["sync"]["status"] == "OutOfSync"
        time.sleep(3)
    print("PASS: production drift retained for 45 seconds without automatic sync", flush=True)
    evidence["checks"]["production_drift_detected_and_held"] = True
    sync("production-hello")
    assert resource("deployment", "hello", "production-hello")["spec"]["replicas"] == intended_replicas
    evidence["checks"]["production_explicit_sync_restored_git"] = True
    for name in ["platform-bootstrap", "staging-hello", "production-hello"]:
        wait(name)
    evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
    output = ROOT / "generated/gitops-proof.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"PASS: reconciliation policies verified; evidence: {output}", flush=True)


if __name__ == "__main__":
    run()
