# Observed GitOps verification

Verified against the running four-node Talos cluster on **2026-10-22 11:32:24 CEST**.

## Git creates the applications

[Bootstrap commit `d3e595f`](https://github.com/naiin/devPlatformDeveloper/commit/d3e595f320c04f9b2e3517d75c197edcadb6a1bd)
introduced the root Application, two AppProjects for workloads, and two Git-file
ApplicationSets. The bootstrap Application reconciled its Git directory;
ApplicationSets generated `staging-hello` and `production-hello`. Staging deployed
automatically. Production initially remained OutOfSync/Missing until the initial
explicit sync.

## A Git commit updates an application

[Values-change commit `c32b0c0`](https://github.com/naiin/devPlatformDeveloper/commit/c32b0c0aa26550f2d50719d3e86266bc9a68f30d)
changed only `gitops/environments/staging/hello/values.yaml`.

| Observation | Before | After Git reconciliation |
| --- | --- | --- |
| Deployment replicas | 1 | 2 |
| ConfigMap message | Staging baseline managed by Git and Argo CD. | Staging revision 2: deployed by a Git commit through Argo CD. |
| Argo sync revision | `d3e595f` | `c32b0c0` |
| Sync operation initiated automatically | — | `true` |
| Final sync / health | Synced / Healthy | Synced / Healthy |

The operation's `syncResult.revision` matched the exact pushed commit SHA.
No kubectl apply, Helm upgrade, or explicit Argo sync was used to deploy this
staging update.

## Manual drift follows the environment policy

| Test | Observed outcome |
| --- | --- |
| Patch staging's managed ConfigMap message | Application changed from Synced to OutOfSync; Argo automatically restored the Git message and returned to Synced. |
| Scale production from 2 to 3 replicas | Argo detected OutOfSync and retained the manual scale for 45 seconds without auto-sync. |
| Explicit production sync | Argo restored 2 replicas from the reviewed Git revision; application returned to Synced and Healthy. |

The repeatable test is `python3 scripts/gitops-verify.py`. Machine-readable
runtime evidence is kept locally in `generated/gitops-proof.json` and
`generated/gitops-git-change.json`; these generated artifacts are not committed.

## Running installation

- Helm chart: `argo/argo-cd` **10.10.5**.
- Argo CD image: `quay.io/argoproj/argocd:v3.5.6`.
- Project workload chart: `hello` **0.1.0**.
- Workload image: `traefik/whoami:v1.11.0`.
- Bootstrap, staging, and production Applications finished **Synced / Healthy**.
- Argo UI authentication and API access through `/argocd/` passed.
- `/staging` and `/production` returned **HTTP 200** through Traefik.

This records observations from the actual cluster, not a simulated reconciliation.
