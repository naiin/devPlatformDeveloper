# Observed application and release verification

Verified on **2026-10-22 12:14:37 CEST** against the running Talos cluster.

## Merge, tests, scans, image publication, and staging

- [Implementation PR #1](https://github.com/naiin/devPlatformDeveloper/pull/1) passed hosted checks and was merged.
- [PR CI run](https://github.com/naiin/devPlatformDeveloper/actions/runs/39760776875) passed tests, lint, static analysis, dependency audit, Helm validation, secret scan, and runtime image scan.
- [Merge-triggered build](https://github.com/naiin/devPlatformDeveloper/actions/runs/39761053052) independently passed both jobs and published **v0.1.2** and the source-SHA image tag to GHCR.
- Runtime image: `ghcr.io/naiin/devplatformdeveloper-api@sha256:c7295d1ad30abfa1aa3ae7aaf323109e162a2e03665db61ba192ed389046aeae`.
- Tested source commit: `5c8d507f4fa99707741121c724b9220d20d9d044`.
- CI committed that digest into staging's Helm values. Argo CD discovered `staging-platform` and automatically deployed it; no local Helm install or kubectl apply deployed the workload.
- The running Deployment uses that exact digest. Its readiness API reports **v0.1.2**.
- Hosted tests cover 21 cases, including outbox/Redis failure recovery, idempotent replay, snapshot isolation, approved rollback, and rejection of unapproved rollback targets.
- pip-audit found no known runtime dependency vulnerabilities; Trivy reported zero fixable HIGH/CRITICAL runtime findings. Build-only installers were removed instead of suppressing their findings. Security scan output, test reports, and the SBOM are available as build artifacts.

## Actual queue and persistence proof

A request to staging traversed ingress, FastAPI, PostgreSQL's durable outbox,
Redis Streams, the worker, and PostgreSQL's stored result. The result was correct
and processed once. The PostgreSQL pod was then deleted and recreated. The
same result remained available through the API using the same bound PVC.
The PV's actual reclaim policy is **Retain**. All staging pods returned Ready.

Repeat: `python3 scripts/app-verify.py --restart-postgres`.

API documentation: **http://demo.talos.test/api/staging/docs**.

## Production approval and rollback

[Promotion PR #2](https://github.com/naiin/devPlatformDeveloper/pull/2) proposes
this exact staged artifact. It changes only the production candidate record;
it does not change production's live Helm values or Application revision.

The actual GitHub `production` environment has required reviewer **naiin**,
administrator bypass disabled, and a deployment branch policy permitting only
`main`. Actions' repository-wide PR approval permission remains disabled.
After the candidate PR is merged, the production job must pass environment
review before it can publish an approved snapshot and activate its Git pointer.
**Production is intentionally not deployed yet; no `production-platform`
Application exists before approval.**

The approved source snapshot is based on the CI-tested source SHA rather than
whatever chart happens to be newest on main. Rollback uses the same review gate
and rejects targets that are not approved snapshots. Successful rollback and
both unapproved-source and wrong-main-commit rejection were exercised by unit
tests; no production rollout or live production rollback was performed.

The original hello demonstrations remain healthy. Bootstrap, staging-hello,
production-hello, and staging-platform all finished Synced and Healthy.
