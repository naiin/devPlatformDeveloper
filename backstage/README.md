# DevPlatform Backstage

Official Backstage application generated with `@backstage/create-app@0.9.3`, release 1.56.0, Node 22.22.3, Yarn 4.13.0. `yarn.lock` pins the dependency graph. The portal uses a separate PostgreSQL instance and retained local-path PVC.

## GitHub setup

Create a GitHub App owned by `naiin` using [this prefilled setup page](https://github.com/settings/apps/new?name=naiin-devplatform-backstage&url=http%3A%2F%2Fdemo.talos.test%2Fbackstage&description=DevPlatform+service+scaffolding+and+reviewed+GitOps+onboarding&callback_urls%5B%5D=http%3A%2F%2Fdemo.talos.test%2Fbackstage%2Fapi%2Fauth%2Fgithub%2Fhandler%2Fframe&public=false&webhook_active=false&administration=write&contents=write&workflows=write&pull_requests=write). Review the requested permissions before creating it.

- Homepage: `http://demo.talos.test/backstage`
- Callback: `http://demo.talos.test/backstage/api/auth/github/handler/frame`
- Disable webhooks (polling is used).
- Repository permissions: Administration, Contents, Workflows, Pull requests **read/write**; Metadata read.
- Install on your `naiin` account. Select all repositories if newly generated repositories should become accessible automatically; otherwise add each generated repository to its installation.
- Generate a client secret and private key. Copy `backstage/github-config.example.yaml` to `generated/backstage-github.yaml`, fill it locally, and run `chmod 600 generated/backstage-github.yaml`.
- Never paste private keys or client secrets into chat or commit them.

Deploy with `python3 scripts/backstage-bootstrap.py --image ghcr.io/naiin/devplatform-backstage@sha256:ACTUAL_DIGEST --github-config generated/backstage-github.yaml`. The script preserves existing database passwords. It stores the App configuration only in a Kubernetes Secret. The credentials mount is loaded after base configuration. No personal CLI token is copied into the portal.

Without GitHub configuration, guest access is read-only. GitHub sign-in resolves catalog usernames; only `user:default/naiin` may run templates or mutate catalog state. Adding more developers requires an explicit permission-policy change. The lab URL uses HTTP; keep it on your private lab network.

## Create a service

Sign in through GitHub, open **Create**, choose **Create FastAPI Microservice**, supply a unique lowercase service name and description. The template creates a public repository, copies the real tested FastAPI/Redis worker/PostgreSQL implementation and hash-locked Python dependencies, generates CI/Helm/catalog definitions, registers the component and opens an onboarding PR.

The onboarding PR targets the protected `onboarding` branch of `naiin/devPlatformDeveloper`. Its required validation check restricts edits to one well-formed discovery file per service. One human approval is required, including for administrators. App-authored PRs allow `naiin` to approve them. No portal or Actions identity is given an approval bypass. The separate branch preserves existing main-branch CI staging updates.

Before merge, the operator runs `python3 scripts/onboarding-prepare.py SERVICE` to create that service’s namespace and random credentials outside Git. Then approve and merge the onboarding PR. After merge, the `onboarded` ApplicationSet discovers `gitops/onboarded/*/app.yaml`, reads that service repository's Helm chart and staging values, and reconciles into `staging-SERVICE`. Every main code merge in the generated repository runs tests/scans, publishes a versioned GHCR image and updates that repository's staging values. The service URL is `http://demo.talos.test/services/SERVICE/docs`. Ensure the GHCR package is public or configure a pull secret before its first deployment; GitHub defaults newly created packages to private.

Production onboarding is deliberately separate: this template activates staging only. Existing production approval/release behavior remains managed by the release workflow.

## Operations and limitations

- Bootstrap: `scripts/backstage-bootstrap.py`; remove portal workloads with `scripts/kubectl delete -f gitops/backstage/resources.yaml` only when intentionally retiring the portal. PVCs must be retained separately before namespace deletion.
- Database storage survives pod recreation, not a lost VM disk. Back up PostgreSQL before destroying infrastructure.
- The portal has no Kubernetes API permissions and no mounted service account token. Operator credential preparation is explicit, scoped to the named service, and preserves existing credentials.
- A failed task can leave a repository or namespace. Retry with a fresh service name after inspecting the task; clean partial resources intentionally. Task execution across GitHub/Kubernetes is not transactional.
- The template preserves the tested application package name `platform_app`; the repository, image, namespace, URL, and catalog identity are customized.
- Build: `cd backstage && node .yarn/releases/yarn-4.13.0.cjs install --immutable && node .yarn/releases/yarn-4.13.0.cjs tsc && node .yarn/releases/yarn-4.13.0.cjs build:backend`. Hosted CI publishes the portal image and a `backstage-SHA` mirror in the existing public lab GHCR package (`devplatformdeveloper-api`), so lab nodes can pull anonymously. Deployment pins the mirror digest. New generated service packages still need to be made public once or supplied with a pull secret.
