#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
for tool in terraform VBoxManage python3 curl helm ip; do
  command -v "$tool" >/dev/null || { echo "Required command missing: $tool" >&2; exit 1; }
done
terraform init
terraform apply "$@"
ip=$(terraform output -raw ingress_ip)
hostname=$(terraform output -raw demo_url)
hostname=${hostname#http://}
if sudo -n true 2>/dev/null; then
  sudo -n python3 scripts/hosts.py --ip "$ip" --hostname "$hostname"
else
  echo "To finish browser DNS, run: sudo python3 '$PWD/scripts/hosts.py' --ip '$ip' --hostname '$hostname'"
fi

