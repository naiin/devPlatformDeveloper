#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
export KUBECONFIG="${KUBECONFIG:-$PWD/generated/kubeconfig}"
: "${INGRESS_IP:=192.168.57.200}"
: "${DEMO_HOSTNAME:=demo.talos.test}"
kubectl="$PWD/.cache/kubectl"
# Wait for all four registrations as well as readiness; --all alone can pass
# when the API has registered only the first node.
deadline=$((SECONDS + 900))
until [[ "$("$kubectl" get nodes -o name 2>/dev/null | wc -l)" -eq 4 ]]; do
  (( SECONDS < deadline )) || { echo "Timed out waiting for all four nodes" >&2; exit 1; }
  sleep 5
done
"$kubectl" wait --for=condition=Ready nodes --all --timeout=900s
"$kubectl" label nodes --selector='!node-role.kubernetes.io/control-plane' \
  node-role.kubernetes.io/worker= --overwrite
helm repo add metallb https://metallb.github.io/metallb --force-update
helm repo add traefik https://traefik.github.io/charts --force-update
helm repo update metallb traefik
"$kubectl" create namespace metallb-system --dry-run=client -o yaml | "$kubectl" apply -f -
"$kubectl" label namespace metallb-system \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/audit=privileged \
  pod-security.kubernetes.io/warn=privileged --overwrite
helm upgrade --install metallb metallb/metallb --version 0.16.1 \
  --namespace metallb-system --set speaker.frr.enabled=false \
  --set frrk8s.enabled=false --wait --timeout 10m
cat > generated/metallb-pool.yaml <<EOF
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: lab
  namespace: metallb-system
spec:
  addresses:
    - "$INGRESS_IP-${INGRESS_IP%.*}.219"
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: lab
  namespace: metallb-system
spec:
  ipAddressPools: [lab]
EOF
"$kubectl" apply -f generated/metallb-pool.yaml
helm upgrade --install traefik traefik/traefik --version 42.1.2 \
  --namespace traefik --create-namespace --values manifests/traefik-values.yaml \
  --set-string "service.annotations.metallb\\.io/loadBalancerIPs=$INGRESS_IP" \
  --wait --timeout 10m
"$kubectl" apply -f manifests/demo.yaml
cat > generated/demo-ingress.yaml <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: whoami
  namespace: demo
spec:
  ingressClassName: traefik
  rules:
    - host: $DEMO_HOSTNAME
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: whoami
                port:
                  number: 80
EOF
"$kubectl" apply -f generated/demo-ingress.yaml
"$kubectl" -n demo rollout status deployment/whoami --timeout=300s
deadline=$((SECONDS + 180))
until curl --noproxy '*' --fail --silent --show-error --connect-timeout 3 --max-time 5 \
  --resolve "$DEMO_HOSTNAME:80:$INGRESS_IP" "http://$DEMO_HOSTNAME" > generated/demo-response.txt; do
  (( SECONDS < deadline )) || { echo "Ingress HTTP check failed" >&2; exit 1; }
  sleep 3
done
python3 scripts/hosts.py --ip "$INGRESS_IP" --hostname "$DEMO_HOSTNAME" --write-instructions
echo "Cluster and ingress verified. Browser URL: http://$DEMO_HOSTNAME"

