# Argo CD GitOps

Git repository: https://github.com/naiin/devPlatformDeveloper, branch `main`.
The [FastAPI release pipeline](../app/README.md) extends this setup with an
approval-gated, immutable production snapshot; see [observed release proof](../docs/application-proof.md).
Argo reads this public repository over HTTPS; no Git credentials or cluster
secrets are committed. Pushes use your workstation's existing SSH authentication.

## Bootstrap

```bash
./scripts/gitops-bootstrap.sh
python3 scripts/gitops.py wait platform-bootstrap
python3 scripts/gitops.py wait staging-hello
python3 scripts/gitops.py sync production-hello
```

The initial installation pins Helm chart **10.10.5** and Argo CD **v3.5.6** in
`versions.env` and `platform/argocd-values.yaml`. The version override deliberately
uses v3.5.6 rather than the chart's v3.5.5 default. Other chart images are pinned
by that exact upstream Helm release. The workload chart is version **0.1.0** and
its container image is pinned to **traefik/whoami:v1.11.0**.

Argo CD UI: **http://demo.talos.test/argocd/**. Sign in as `admin`; retrieve the
password locally with `cat generated/argocd-admin-password`. This file is private
and ignored by Git. The lab UI uses the existing private-network HTTP ingress.
Production-grade TLS/SSO and a highly available Argo installation are outside this
single-control-plane development lab.

The installer applies the project declarations and root Application once. The
root Application subsequently reconciles `bootstrap/` from Git, including the
two environment projects and ApplicationSets. Argo CD's own installation is
managed by the pinned bootstrap Helm script, not by the root Application.

```text
gitops/
  root.yaml                              bootstrap Application
  bootstrap/
    projects.yaml                        allowed repositories/resources/namespaces
    staging-applicationset.yaml           Git file generator; auto sync/self-heal
    production-applicationset.yaml        Git file generator; explicit sync
  charts/hello/                          project Helm chart, version 0.1.0
  environments/staging/hello/
    app.yaml                             ApplicationSet discovery metadata
    values.yaml                          staging project values
  environments/production/hello/
    app.yaml                             ApplicationSet discovery metadata
    values.yaml                          production project values
  platform/                              pinned Argo installation values/ingress
```

## Environment policies

| Environment | Git update | Manual drift | Pruning |
| --- | --- | --- | --- |
| Bootstrap | Automatically applies | Automatically repairs | Enabled within root application |
| Staging | Automatically applies | Automatically repairs | Enabled within application |
| Production hello demo | Shows OutOfSync; explicit sync required | Shows OutOfSync; retained until explicit sync | Only during explicit sync with pruning |
| Production platform service | Deploys only an immutable revision activated after GitHub environment approval | Repairs drift against that approved revision | Within the approved application; PVCs are retained |

Repository polling runs roughly every 30–35 seconds. ApplicationSet Git
generators poll every 30 seconds. Automatic self-healing uses a 10-second retry
interval. Kubernetes watch events can detect drift sooner than polling.

The projects restrict deployment to `staging-*` and `production-*` namespaces
and an explicit resource allowlist, including the platform's StatefulSets,
PVCs, migration Jobs, and ingress Middleware. The bootstrap project can manage AppProjects
and ApplicationSets only in `argocd`. Generated Applications preserve workloads
if their ApplicationSet entry is removed: deletion is intentionally a separate,
reviewed operation. A production Application is not an approval system by
itself—repository reviews, Kubernetes access, and Argo RBAC govern who may sync.

## Change or add an application

Edit the appropriate `environments/<environment>/<app>/values.yaml`, commit,
and push `main`. Argo renders the Helm chart using that environment's values.
Adding another directory containing `app.yaml` creates an Application through
the matching ApplicationSet; set its `name`, `chartPath`, and `valuesFile`.
The values path is relative to the Helm chart directory.

Staging endpoint: **http://demo.talos.test/staging**.
Production endpoint: **http://demo.talos.test/production**.

To promote, review the staging values and apply the intended change to the
production values in a separate Git commit. After it reaches `main`, inspect
the Argo diff and explicitly sync:

```bash
python3 scripts/gitops.py status
python3 scripts/gitops.py refresh production-hello
python3 scripts/gitops.py sync production-hello
```

The sync helper pins the operation to the exact Git SHA Argo has already
resolved. It uses your existing Kubernetes credentials and never stores an
Argo API token. Workload chart changes apply to staging automatically;
production remains gated by explicit sync.

## Verification

The completed Git-change demonstration and observed commit SHA are recorded in
`proof.md`. The repeatable drift test is:

```bash
python3 scripts/gitops-verify.py
```

It changes only these dedicated demonstration workloads: it patches staging's
ConfigMap, observes OutOfSync and automatic restoration, scales production
temporarily, verifies production retains the drift for 45 seconds, and then
explicitly syncs production back to Git. Evidence is written to
`generated/gitops-proof.json`. Both Applications finish Synced and Healthy.

Do not commit `generated/`, Terraform state, cached plans, kubeconfig, SSH keys,
or passwords. The repository's `.gitignore` excludes these local artifacts.

References: [automated sync and self-heal](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/),
[Git ApplicationSet generators](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Generators-Git/),
[project restrictions](https://argo-cd.readthedocs.io/en/stable/user-guide/projects/).

