#!/usr/bin/env python3
"""Verify ingress, queued work, and PostgreSQL persistence across a pod restart."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(url, data=None):
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=headers)
    with HTTP.open(req, timeout=10) as response:
        return json.load(response)


def eventually(callback, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = callback()
            if value:
                return value
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError("Timed out waiting for application result")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["staging", "production"], default="staging")
    parser.add_argument("--restart-postgres", action="store_true")
    args = parser.parse_args()
    base = f"http://demo.talos.test/api/{args.environment}"
    namespace = args.environment + "-platform"
    ready = eventually(lambda: request(base + "/health/ready"))
    payload = "PostgreSQL persistence " + str(time.time_ns())
    job = request(base + "/jobs", {"text": payload, "operation": "uppercase"})
    result = eventually(lambda: (r if (r := request(base + "/jobs/" + job["id"]))["status"] == "completed" else None))
    assert result["result"] == payload.upper() and result["attempts"] == 1
    print("PASS: ingress -> FastAPI -> PostgreSQL outbox -> Redis -> worker -> persisted result")
    proof = {"version": ready["version"], "job_id": job["id"], "result": result["result"],
             "environment": args.environment, "persistence_restart_verified": False}
    if args.restart_postgres:
        command = [str(ROOT / "scripts/kubectl"), "-n", namespace]
        pvc = json.loads(subprocess.check_output(command + ["get", "pvc", "platform-postgres", "-o", "json"], text=True))
        assert pvc["status"]["phase"] == "Bound"
        subprocess.run(command + ["delete", "pod", "platform-postgres-0", "--wait=true"], check=True)
        subprocess.run(command + ["rollout", "status", "statefulset/platform-postgres", "--timeout=300s"], check=True)
        persisted = eventually(lambda: request(base + "/jobs/" + job["id"]))
        assert persisted["result"] == result["result"] and persisted["attempts"] == 1
        proof.update(persistence_restart_verified=True, pvc_uid=pvc["metadata"]["uid"],
                     persistent_volume=pvc["spec"]["volumeName"])
        print("PASS: job result survives PostgreSQL pod deletion and recreation using its PVC")
    proof["verified_at"] = datetime.now(timezone.utc).isoformat()
    (ROOT / f"generated/platform-{args.environment}-proof.json").write_text(json.dumps(proof, indent=2) + "\n")


if __name__ == "__main__":
    main()
