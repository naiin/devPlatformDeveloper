#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
source gitops/versions.env
export KUBECONFIG="$PWD/generated/kubeconfig"
mkdir -p generated .runtime
helm repo add argo https://argoproj.github.io/argo-helm --force-update
helm upgrade --install argocd argo/argo-cd --version "$ARGOCD_CHART_VERSION" \
  --namespace argocd --create-namespace --values gitops/platform/argocd-values.yaml \
  --set-string global.image.tag="$ARGOCD_VERSION" --wait --timeout 10m
./scripts/kubectl apply -f gitops/platform/argocd-ingress.yaml
# The root project must exist before its Application can reconcile the Git path.
./scripts/kubectl apply -f gitops/bootstrap/projects.yaml
./scripts/kubectl apply -f gitops/root.yaml
./scripts/kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode > generated/argocd-admin-password
chmod 600 generated/argocd-admin-password
echo 'Argo CD UI: http://demo.talos.test/argocd/'
echo 'User: admin; password is stored in generated/argocd-admin-password (not printed).'
echo 'Production requires explicit sync: python3 scripts/gitops.py sync production-hello'

