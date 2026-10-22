#!/usr/bin/env python3
"""Git-only staging, promotion PRs, approved production releases, and rollback."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPO = "naiin/devPlatformDeveloper"
IMAGE = "ghcr.io/naiin/devplatformdeveloper-api"


def run(*args, **kwargs):
    return subprocess.check_output(list(args), text=True, cwd=ROOT, **kwargs).strip()


def checked_sha(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("A full immutable Git SHA is required")
    return value


def validate(candidate):
    checked_sha(candidate["source"])
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate["digest"]):
        raise ValueError("An immutable SHA256 image digest is required")
    if candidate["image"] != IMAGE or not re.fullmatch(r"v\d+\.\d+\.\d+", candidate["version"]):
        raise ValueError("Unexpected image repository or release version")


def save(path, data):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def commit(paths, message):
    run("git", "add", "--", *paths)
    if run("git", "diff", "--cached", "--name-only"):
        run("git", "commit", "-m", message)
    return run("git", "rev-parse", "HEAD")


def update_values(environment, candidate):
    path = ROOT / f"gitops/environments/{environment}/platform/values.yaml"
    values = yaml.safe_load(path.read_text())
    values["image"] = {"repository": candidate["image"], "tag": candidate["version"],
                       "digest": candidate["digest"]}
    path.write_text(yaml.safe_dump(values, sort_keys=False))


def write_app(environment, revision="main", automatic=False):
    data = {"name": "platform", "chartPath": "gitops/charts/platform",
            "valuesFile": f"../../environments/{environment}/platform/values.yaml"}
    if environment == "production":
        data.update(revision=checked_sha(revision), autoSync=automatic)
    path = ROOT / f"gitops/environments/{environment}/platform/app.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def stage(args):
    candidate = {"image": IMAGE, "digest": args.digest, "version": args.version,
                 "source": checked_sha(args.source), "build_url": args.build_url}
    validate(candidate)
    update_values("staging", candidate)
    write_app("staging")
    save("releases/staging.json", candidate)
    commit(["gitops/environments/staging/platform", "releases/staging.json"],
           f"Deploy {args.version} to staging [skip ci]")


def promote():
    # Run by the operator with their existing gh login, rather than granting
    # GITHUB_TOKEN permission to create/approve PRs in this public repository.
    if run("git", "status", "--porcelain"):
        raise RuntimeError("Commit or stash local changes before opening a promotion PR")
    run("git", "fetch", "origin", "main")
    candidate = json.loads(run("git", "show", "origin/main:releases/staging.json"))
    validate(candidate)
    branch = "promote/" + candidate["version"]
    original = run("git", "branch", "--show-current")
    run("git", "switch", "-c", branch, "origin/main")
    try:
        save("releases/production/candidate.json", candidate)
        commit(["releases/production/candidate.json"],
               f"Propose {candidate['version']} for production")
        run("git", "push", "--set-upstream", "origin", branch)
        body = (f"Promote staging image `{candidate['image']}@{candidate['digest']}`.\n\n"
                f"Version: `{candidate['version']}`\nSource: `{candidate['source']}`\n"
                f"Build and scan evidence: {candidate['build_url']}\n\n"
                "Merging this PR does not deploy production. The production release job "
                "must separately pass the required GitHub environment review. "
                "It then publishes an immutable approved Git revision for Argo CD.\n")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md") as file:
            file.write(body)
            file.flush()
            print(run("gh", "pr", "create", "--repo", REPO, "--base", "main", "--head", branch,
                      "--title", f"Promote {candidate['version']} to production", "--body-file", file.name))
    finally:
        run("git", "switch", original)


def approve(args):
    candidate = json.loads(run("git", "show", f"{checked_sha(args.candidate_ref)}:releases/production/candidate.json"))
    validate(candidate)
    # This entry point is invoked only by a job protected by the production
    # GitHub Environment. The earlier candidate PR never changes live values.
    candidate.update(approved_run=args.run_url,
                     approved_at=datetime.now(timezone.utc).isoformat())
    original = run("git", "branch", "--show-current")
    # Build the approved snapshot from the exact source that passed CI. A new
    # main-branch chart edit must never sneak into an older approved release.
    run("git", "switch", "--detach", candidate["source"])
    update_values("production", candidate)
    save("releases/production/approved.json", candidate)
    revision = commit(["gitops/environments/production/platform/values.yaml",
                       "releases/production/approved.json"],
                      f"Approve production {candidate['version']} [skip ci]")
    suffix = args.run_url.rstrip("/").split("/")[-1]
    snapshot = f"refs/heads/releases/production/{candidate['version']}-{suffix}"
    run("git", "push", "origin", f"{revision}:{snapshot}")
    run("git", "switch", original)
    update_values("production", candidate)
    save("releases/production/approved.json", candidate)
    write_app("production", revision=revision, automatic=True)
    commit(["gitops/environments/production/platform", "releases/production/approved.json"],
           f"Activate approved production revision {revision[:12]} [skip ci]")
    print(f"Approved immutable deployment revision: {revision}")


def rollback(args):
    revision = checked_sha(args.revision)
    approved = json.loads(run("git", "show", f"{revision}:releases/production/approved.json"))
    validate(approved)
    if run("git", "rev-parse", f"{revision}^") != approved["source"]:
        raise ValueError("Rollback target is not an approved source snapshot")
    changed = set(run("git", "diff", "--name-only", f"{revision}^", revision).splitlines())
    allowed = {"gitops/environments/production/platform/values.yaml", "releases/production/approved.json"}
    if not changed.issubset(allowed):
        raise ValueError("Approved snapshot contains unexpected source changes")
    update_values("production", approved)
    write_app("production", revision=revision, automatic=True)
    save("releases/production/rollback.json", {"revision": revision, "run_url": args.run_url,
                                              "at": datetime.now(timezone.utc).isoformat()})
    commit(["gitops/environments/production/platform", "releases/production/rollback.json"],
           f"Roll back production to {revision[:12]} [skip ci]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    staging = commands.add_parser("stage")
    for name in ["digest", "version", "source", "build-url"]:
        staging.add_argument("--" + name, required=True)
    commands.add_parser("promote")
    release = commands.add_parser("approve")
    release.add_argument("--run-url", required=True)
    release.add_argument("--candidate-ref", required=True)
    back = commands.add_parser("rollback")
    back.add_argument("--revision", required=True)
    back.add_argument("--run-url", required=True)
    options = parser.parse_args()
    {"stage": stage, "promote": lambda _: promote(), "approve": approve,
     "rollback": rollback}[options.command](options)
