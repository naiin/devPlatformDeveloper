# Backstage implementation and verification

Portal: http://demo.talos.test/backstage/

- Backstage release 1.56.0, generated with create-app 0.9.3; Node 22.22.3 and Yarn 4.13.0; dependency graph locked in `backstage/yarn.lock`.
- Portal image source: `1de78408abe3873a7ac727fe2aee3585bd80df46`.
- Image: `ghcr.io/naiin/devplatformdeveloper-api@sha256:95c640a65fb83dec70bd3ca1e80b0362869e88a3a54b7093ecc5fc91d7fba294` (public lab mirror).
- Successful [portal image build](https://github.com/naiin/devPlatformDeveloper/actions/runs/39805848581), including immutable dependency install, TypeScript check, frontend/backend build and Docker image publication.
- Existing application tests and security checks also passed on the implementation PR.
- Dedicated `backstage-postgres-0`, 2Gi retained local-path PVC. Confirmed plugin databases for catalog, scaffolder, auth, search and other installed plugins exist in PostgreSQL.
- GitHub `onboarding` branch protection: one approving review, stale-review dismissal, last-push approval, required `Validate onboarding` status, strict checks, administrator enforcement, conversation resolution, no force pushes or branch deletion.
- Validator smoke check accepted valid discovery and rejected a repository outside `naiin`.
- Backstage deployment has `automountServiceAccountToken: false`; no onboarding ClusterRole or ClusterRoleBinding exists.

`node scripts/backstage-verify.cjs` verifies the catalog UI, Create FastAPI Microservice template UI/catalog registration, and HTTP 403 for guest task creation. It writes private local proof JSON and screenshots under `generated/`.

## Remaining end-to-end verification

GitHub App credentials are not configured yet. Repository creation, GitHub sign-in, App-authored protected onboarding PR creation, and deployment of a newly generated repository cannot be verified until the owner creates/installs the App and runs `python3 scripts/backstage-github-setup.py`. No private credentials belong in chat or Git.

The portal is intentionally unprivileged. Automatic approval review rejected cluster-wide namespace/Secret creation permission; that permission was removed. Before merging each generated onboarding PR, an operator runs `python3 scripts/onboarding-prepare.py SERVICE` and makes the generated GHCR package public (or configures a pull secret). After that initial preparation and required PR approval, Argo CD automatically discovers/reconciles staging and subsequent successful service CI builds update its desired image through Git.
