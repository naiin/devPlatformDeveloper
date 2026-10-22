# Durable jobs and release pipeline

The API stores jobs in PostgreSQL before accepting them. The worker publishes
the queued rows into Redis Streams, processes messages, and commits results to
PostgreSQL before acknowledging them. Row locks and terminal-state checks make
redelivery safe. Queued rows are republished after 60 seconds if Redis loses data.

Swagger UI: `http://demo.talos.test/api/staging/docs`.

```bash
curl -X POST http://demo.talos.test/api/staging/jobs \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello from GitOps","operation":"uppercase"}'
curl http://demo.talos.test/api/staging/jobs/JOB_ID
```

Operations are `uppercase` and `reverse`; text is limited to 10,000 characters.
`GET /jobs?limit=20` lists recent jobs. `/health/live` checks the API process;
`/health/ready` checks PostgreSQL and Redis. Worker readiness checks its own
Redis heartbeat. This is a development-lab API with no end-user authentication.

## Tests and local build

```bash
docker compose -f compose.test.yaml build tests
docker compose -f compose.test.yaml run --rm tests
docker compose -f compose.test.yaml down --volumes
```

The suite includes input validation, transformation behavior, real PostgreSQL
and Redis round trips, transactional outbox rollback, duplicate delivery after
commit-before-ACK, Redis data-loss recovery, immutable production chart snapshots,
and approved-version rollback. Runtime and test dependencies are hash locked.
The runtime and database base images are pinned by digest.

## Merge to staging

`.github/workflows/ci.yml` runs on application PRs and merges to `main`:

1. Run Ruff, Bandit, unit tests, and PostgreSQL/Redis integration tests.
2. Audit runtime dependencies with pip-audit and lint both environment Helm values.
3. Build a non-root runtime image; scan secrets and fixable HIGH/CRITICAL image
   vulnerabilities with checksum-verified Trivy 0.76.1. Failed scans stop publishing.
4. Upload test results, image scan output, and a CycloneDX SBOM as Actions artifacts.
5. On main, publish `ghcr.io/naiin/devplatformdeveloper-api:v0.1.RUN_NUMBER` and
   `sha-FULL_GIT_SHA` tags. A `vX.Y.Z` Git tag publishes that explicit version.
6. Commit the immutable image digest to staging's Helm values and create its
   ApplicationSet discovery file. Argo CD deploys the Git change automatically.

PR builds scan the image but do not publish it. The same image is used for API,
worker, and Alembic migrations; promotion never rebuilds it. The CI job does not
need network access to the local Kubernetes API. Git is the deployment trigger.
Make the GHCR package public for anonymous cluster pulls, or provision a separate
read-only image-pull Secret before using private images. No expiring Actions token
is stored in Kubernetes.

## Promotion PR and explicit production approval

With a clean checkout and your existing `gh` authentication:

```bash
git switch main && git pull --ff-only
python3 scripts/release.py promote
```

This opens a PR containing the staging version, source SHA, build evidence URL,
and image digest in `releases/production/candidate.json`. It does not change the
production deployment. Review and merge the candidate PR, then approve the
**production** environment job in GitHub Actions.

The GitHub production environment requires **naiin** as reviewer, permits only
`main`, and disables administrator bypass. Because this repository has only one
collaborator, that account can explicitly approve a release it requested.
Actions' permission to create/approve PRs remains disabled; the operator creates
promotion PRs using their existing login.

Only after review does `production.yml` create a release snapshot from the exact
source commit that passed CI, containing the approved production Helm values.
The snapshot is retained on a `releases/production/...` branch. A second main
commit points `production-platform` to its immutable Git SHA. Argo automatically
deploys that approved snapshot and repairs drift against it. Future ordinary main
merges cannot change its chart, image, or values. The existing `production-hello`
demonstration retains its original explicit-sync policy.

## Rollback

Select a previously approved source revision from the production Application
history or a `releases/production/...` branch, then:

```bash
gh workflow run production.yml --ref main -f rollback_revision=FULL_APPROVED_GIT_SHA
```

The same production environment review is required. The job rejects a revision
without an approved-release receipt, updates the production Git pointer and
visible values, and lets Argo reconcile the previous immutable image/chart.
It never rebuilds an image, deletes PVCs, or automatically downgrades the database.
Use backward-compatible migrations; data recovery is a separate backup/restore
operation. This lab's retained node-local volumes survive pod recreation, not
loss of the underlying VM disk.

## Cluster bootstrap and verification

```bash
python3 scripts/app-bootstrap.py
python3 scripts/app-verify.py --restart-postgres
```

Bootstrap installs local-path-provisioner v0.0.37 with a Talos-writable path and
Retain policy, then generates separate random database/Redis credentials per
environment. Existing credentials are preserved. They live only in Kubernetes
Secrets; no credentials, state, VM disks, or runtime proof files are committed.
PostgreSQL and Redis run as StatefulSets with retained PVCs. A Sync-wave migration
Job runs after databases become ready and before API/worker Deployments.
