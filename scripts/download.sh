#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
: "${TALOS_VERSION:=v1.14.4}"
: "${KUBERNETES_VERSION:=1.37.1}"
target="$PWD/.cache/$TALOS_VERSION"
mkdir -p "$target" .runtime generated
base="https://github.com/siderolabs/talos/releases/download/$TALOS_VERSION"
fetch() {
  local name="$1"
  if [[ ! -s "$target/$name" ]]; then
    curl --fail --location --retry 3 --connect-timeout 20 \
      --output "$target/$name.part" "$base/$name"
    mv "$target/$name.part" "$target/$name"
  fi
}
fetch sha256sum.txt
for asset in metal-amd64.iso talosctl-linux-amd64; do
  fetch "$asset"
  (cd "$target"; awk -v name="$asset" '$2 == name || $2 == "*" name {print}' sha256sum.txt > "$asset.sha256")
  [[ -s "$target/$asset.sha256" ]] || { echo "No checksum for $asset" >&2; exit 1; }
  (cd "$target"; sha256sum --check "$asset.sha256")
done
chmod 700 "$target/talosctl-linux-amd64"
# Match kubectl to the Kubernetes minor, without replacing the host's kubectl.
if [[ ! -x "$PWD/.cache/kubectl-$KUBERNETES_VERSION" ]]; then
  curl --fail --location --retry 3 --output .cache/kubectl.part \
    "https://dl.k8s.io/release/v$KUBERNETES_VERSION/bin/linux/amd64/kubectl"
  curl --fail --location --retry 3 --output .cache/kubectl.sha256 \
    "https://dl.k8s.io/release/v$KUBERNETES_VERSION/bin/linux/amd64/kubectl.sha256"
  printf '%s  .cache/kubectl.part\n' "$(cat .cache/kubectl.sha256)" | sha256sum --check
  mv .cache/kubectl.part ".cache/kubectl-$KUBERNETES_VERSION"
  chmod 700 ".cache/kubectl-$KUBERNETES_VERSION"
fi
ln -sfn "kubectl-$KUBERNETES_VERSION" .cache/kubectl

