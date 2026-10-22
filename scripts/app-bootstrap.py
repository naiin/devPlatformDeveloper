#!/usr/bin/env python3
"""Provision local lab storage and random credentials outside the Git repository."""
import base64
import json
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parent.parent
KUBECTL = str(ROOT / "scripts/kubectl")


def apply(data):
    subprocess.run([KUBECTL, "apply", "-f", "-"], input=json.dumps(data), text=True, check=True)


def main():
    subprocess.run([KUBECTL, "apply", "-f", str(ROOT / "gitops/platform/local-path.yaml")], check=True)
    subprocess.run([KUBECTL, "-n", "local-path-storage", "rollout", "status",
                    "deployment/local-path-provisioner", "--timeout=300s"], check=True)
    for namespace in ["staging-platform", "production-platform"]:
        apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace,
               "labels": {"pod-security.kubernetes.io/enforce": "restricted"}}})
        exists = subprocess.run([KUBECTL, "-n", namespace, "get", "secret", "platform-credentials"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if exists:
            print(f"{namespace}: credentials already exist; preserving database passwords")
            continue
        postgres, redis = secrets.token_hex(24), secrets.token_hex(24)
        values = {"POSTGRES_PASSWORD": postgres, "REDIS_PASSWORD": redis,
                  "DATABASE_URL": f"postgresql+psycopg://platform:{postgres}@platform-postgres:5432/platform",
                  "REDIS_URL": f"redis://:{redis}@platform-redis:6379/0"}
        apply({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
               "metadata": {"name": "platform-credentials", "namespace": namespace},
               "data": {key: base64.b64encode(value.encode()).decode() for key, value in values.items()}})
    print("Persistent storage and per-environment credentials are ready; no passwords printed.")


if __name__ == "__main__":
    main()
