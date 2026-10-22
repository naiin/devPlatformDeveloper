#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
kubectl="$PWD/scripts/kubectl"
"$kubectl" get nodes -o json | python3 -c '
import json, sys
nodes = json.load(sys.stdin)["items"]
assert len(nodes) == 4, f"Expected four nodes, got {len(nodes)}"
cp = [n for n in nodes if "node-role.kubernetes.io/control-plane" in n["metadata"]["labels"]]
assert len(cp) == 1, f"Expected one control plane, got {len(cp)}"
for node in nodes:
    assert any(c["type"] == "Ready" and c["status"] == "True" for c in node["status"]["conditions"]), node["metadata"]["name"]
print("PASS: one control plane and three workers, all Ready")
'
"$kubectl" -n demo get pods -l app=whoami -o json | python3 -c '
import json, sys
pods = [p for p in json.load(sys.stdin)["items"] if not p["metadata"].get("deletionTimestamp")]
assert len(pods) == 3, f"Expected three demo pods, got {len(pods)}"
assert len({p["spec"]["nodeName"] for p in pods}) == 3, "Demo pods should run across all three workers"
assert all(all(c["ready"] for c in p["status"].get("containerStatuses", [])) and p["status"].get("containerStatuses") for p in pods)
print("PASS: demo replicas are healthy across three workers")
'
hostname=$(terraform output -raw demo_url)
hostname=${hostname#http://}
ip=$(terraform output -raw ingress_ip)
actual=$("$kubectl" -n traefik get service traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
[[ "$actual" == "$ip" ]] || { echo "Incorrect LoadBalancer IP: $actual" >&2; exit 1; }
echo "PASS: MetalLB assigned $ip to Traefik"
curl --noproxy '*' --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  --resolve "$hostname:80:$ip" "http://$hostname" | tee generated/demo-response.txt
echo "PASS: HTTP through host-only network, MetalLB, Traefik, and demo service"
resolved=$(getent ahostsv4 "$hostname" | awk 'NR==1 {print $1}')
[[ "$resolved" == "$ip" ]] || { echo "Hosts entry missing or incorrect: $hostname -> $resolved" >&2; exit 1; }
curl --noproxy '*' --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  "http://$hostname" >/dev/null
echo "PASS: /etc/hosts resolution and browser URL http://$hostname"
"$kubectl" get nodes -o wide
"$kubectl" get ingress -A

