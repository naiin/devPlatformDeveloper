"""Release snapshots must not accidentally deploy a newer, untested main chart."""

import argparse
import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

SOURCE = Path(__file__).resolve().parents[3] / "scripts/release.py"
SPEC = importlib.util.spec_from_file_location("release_tool", SOURCE)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


@pytest.fixture
def repository(tmp_path, monkeypatch):
    root = tmp_path / "working"
    root.mkdir()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    monkeypatch.setattr(release, "ROOT", root)
    release.run("git", "init", "-b", "main")
    release.run("git", "config", "user.name", "Release test")
    release.run("git", "config", "user.email", "test@example.test")
    release.run("git", "remote", "add", "origin", str(remote))
    chart = root / "gitops/charts/platform"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text("version: 1.0.0\n")
    for environment in ["staging", "production"]:
        path = root / f"gitops/environments/{environment}/platform"
        path.mkdir(parents=True)
        (path / "values.yaml").write_text("image: {}\n")
    source = release.commit(["gitops"], "Source tested by CI")
    candidate = {
        "image": release.IMAGE,
        "version": "v0.1.1",
        "digest": "sha256:" + "a" * 64,
        "source": source,
        "build_url": "https://example.test/build/1",
    }
    release.save("releases/production/candidate.json", candidate)
    (chart / "Chart.yaml").write_text("version: 9.0.0\n")
    candidate_ref = release.commit(["gitops", "releases"], "Later main chart and promotion PR")
    release.run("git", "push", "origin", "main")
    return root, candidate, candidate_ref


def test_approved_snapshot_uses_tested_chart_and_immutable_digest(repository):
    root, candidate, candidate_ref = repository
    release.approve(
        argparse.Namespace(run_url="https://example.test/runs/123", candidate_ref=candidate_ref)
    )
    pointer = yaml.safe_load(
        (root / "gitops/environments/production/platform/app.yaml").read_text()
    )
    assert pointer["autoSync"] is True
    revision = pointer["revision"]
    assert (
        release.run("git", "show", f"{revision}:gitops/charts/platform/Chart.yaml")
        == "version: 1.0.0"
    )
    assert (root / "gitops/charts/platform/Chart.yaml").read_text() == "version: 9.0.0\n"
    values = yaml.safe_load(
        release.run(
            "git", "show", f"{revision}:gitops/environments/production/platform/values.yaml"
        )
    )
    assert values["image"]["digest"] == candidate["digest"]
    assert (
        release.run(
            "git", "ls-remote", "origin", "refs/heads/releases/production/v0.1.1-123"
        ).split()[0]
        == revision
    )


def test_rollback_rejects_unapproved_source_revision(repository):
    _, candidate, _ = repository
    with pytest.raises(subprocess.CalledProcessError):
        release.rollback(
            argparse.Namespace(
                revision=candidate["source"], run_url="https://example.test/rollback"
            )
        )


def test_rollback_restores_a_previous_approved_digest(repository):
    root, candidate, candidate_ref = repository
    release.approve(
        argparse.Namespace(run_url="https://example.test/runs/123", candidate_ref=candidate_ref)
    )
    path = root / "gitops/environments/production/platform/app.yaml"
    previous = yaml.safe_load(path.read_text())["revision"]
    changed = candidate | {"version": "v0.1.2", "digest": "sha256:" + "b" * 64}
    release.save("releases/production/candidate.json", changed)
    new_ref = release.commit(["releases/production/candidate.json"], "Next candidate")
    release.approve(
        argparse.Namespace(run_url="https://example.test/runs/124", candidate_ref=new_ref)
    )
    assert yaml.safe_load(path.read_text())["revision"] != previous
    release.rollback(argparse.Namespace(revision=previous, run_url="https://example.test/rollback"))
    assert yaml.safe_load(path.read_text())["revision"] == previous
    values = yaml.safe_load(
        (root / "gitops/environments/production/platform/values.yaml").read_text()
    )
    assert values["image"]["digest"] == candidate["digest"]


def test_invalid_candidate_digest_is_rejected():
    with pytest.raises(ValueError, match="digest"):
        release.validate(
            {"source": "a" * 40, "digest": "latest", "image": release.IMAGE, "version": "v0.1.0"}
        )


def test_rollback_rejects_main_commit_even_if_it_contains_a_receipt(repository):
    _, _, candidate_ref = repository
    release.approve(
        argparse.Namespace(run_url="https://example.test/runs/123", candidate_ref=candidate_ref)
    )
    main_sha = release.run("git", "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="snapshot"):
        release.rollback(
            argparse.Namespace(revision=main_sha, run_url="https://example.test/rollback")
        )
