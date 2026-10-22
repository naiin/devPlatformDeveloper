#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
action=${1:-status}
case "$action" in
  status) ./scripts/kubectl get nodes -o wide; ./scripts/kubectl get pods -A; exit ;;
  start|stop) ;;
  *) echo "Usage: $0 [status|start|stop]" >&2; exit 2 ;;
esac
mapfile -t names < <(terraform output -json nodes | python3 -c 'import json,sys; print("\n".join(json.load(sys.stdin)))')
for name in "${names[@]}"; do
  owner=$(VBoxManage getextradata "$name" devPlatform/managed-by)
  [[ "$owner" == "Value: $PWD" ]] || { echo "Refusing unowned VM: $name" >&2; exit 1; }
  state=$(VBoxManage showvminfo "$name" --machinereadable | sed -n 's/^VMState="\(.*\)"$/\1/p')
  if [[ "$action" == start && "$state" != running ]]; then
    VBoxManage startvm "$name" --type headless
  elif [[ "$action" == stop && "$state" == running ]]; then
    # ACPI requests a clean OS shutdown; disks and Terraform state are retained.
    VBoxManage controlvm "$name" acpipowerbutton
  fi
done

