# devPlatformDeveloper

Local Talos Kubernetes on VirtualBox with Argo CD GitOps. See
[the GitOps workflow](gitops/README.md) for bootstrap, staging/production
policies, Helm values, promotion, and the reconciliation demonstration.

The [FastAPI application and release pipeline](app/README.md) adds Redis-backed
jobs, PostgreSQL persistence, tested GHCR images, promotion PRs, required release
approval, and rollback to an immutable approved Git revision.

Terraform creates one control plane and three workers using the official
`siderolabs/talos` provider. A small, ownership-checked `VBoxManage` adapter
creates the VirtualBox VMs and their dedicated host-only network. All VM disks
and generated credentials stay in this project. You can see the VMs in the
normal VirtualBox UI.

| Node | Address | vCPUs | RAM | Thin disk |
| --- | --- | --- | --- | --- |
| talos-lab-cp1 | 192.168.57.10 | 2 | 3 GiB | 40 GiB |
| talos-lab-worker1 | 192.168.57.11 | 2 | 3 GiB | 40 GiB |
| talos-lab-worker2 | 192.168.57.12 | 2 | 3 GiB | 40 GiB |
| talos-lab-worker3 | 192.168.57.13 | 2 | 3 GiB | 40 GiB |

Total VM allocation: 8 vCPUs and 12 GiB RAM. Disks allocate space as written.
Host swap is left as configured; the VMs do not depend on swap for their sizing.
This is a development cluster with a single control plane and no HA or default
persistent-volume provisioner.

Versions: Talos v1.14.4, Kubernetes v1.37.1, Talos Terraform provider v0.12.0,
MetalLB chart 0.16.1, Traefik chart 42.1.2. Provider selections and checksums are
recorded in `.terraform.lock.hcl`. Downloads are verified against release SHA256
checksums. The project supplies matching kubectl and talosctl binaries without
overwriting the workstation's existing tools.

## Access

Open **http://demo.talos.test** in your browser. The page reports the responding
pod and HTTP request. Three demo replicas are spread across the three workers.

```bash
cd /home/hura273929/workspace/devPlatform
./scripts/kubectl get nodes -o wide
./scripts/kubectl get pods -A
./scripts/talosctl health
./scripts/verify.sh
```

To use a separate kubectl explicitly:

```bash
export KUBECONFIG=/home/hura273929/workspace/devPlatform/generated/kubeconfig
```

Prefer `./scripts/kubectl` here: the preinstalled kubectl v1.31 is too old for
this Kubernetes version. Talos has no SSH; use the Talos API through the wrapper.
Generated kubeconfig and talosconfig have mode 0600. Terraform state contains
cluster secrets: keep state and `generated/` private and retain them for future
management. They are ignored by Git.

## Networking and ingress

Each VM has a host-only NIC for cluster traffic and a bridged Intel NIC on the
Ubuntu Wi-Fi interface `wlp0s20f3` for internet access. Configure
`bridge_interface` if you use a different physical interface. Each VM also gets
a DHCP address on your LAN. Host-only DHCP supplies reserved addresses during ISO boot; Talos then
uses the same addresses statically. Kubernetes node IPs and etcd advertise only
the host-only subnet. Guest DNS uses explicit resolvers (1.1.1.1 and 1.0.0.1,
configurable through `dns_servers`). The installed VirtualBox 7.1.4 NAT engine
did not answer gateway ARP, so this setup uses the working bridged uplink.
Existing host-only networks are preserved. The managed interface name is stored
in `.runtime/hostonly-interface`.

MetalLB advertises `192.168.57.200–192.168.57.219` on that network. Traefik uses
`192.168.57.200` and accepts standard Kubernetes `Ingress` resources with
`ingressClassName: traefik`. The demo is plain HTTP on port 80; HTTPS needs your
own certificate configuration. Services are reachable from this Ubuntu host.

The managed hosts entry is:

```text
192.168.57.200 demo.talos.test
```

Update it with the narrowly scoped helper, which preserves unrelated entries
and saves an `/etc/hosts.talos-backup-*` backup:

```bash
sudo python3 scripts/hosts.py
```

For more applications, add their Ingress hostname to `/etc/hosts` at the same
ingress IP and set their Ingress class to `traefik`.

## Create or reconcile

Prerequisites: Ubuntu with functioning VirtualBox 7.x, Terraform >=1.5,
Python 3, curl, Helm 3, `ip`, hardware virtualization enabled, and internet access
for images and providers. Run Terraform as your regular desktop user.

```bash
bash scripts/up.sh
```

The first apply downloads Talos, creates the network and VMs, installs Talos to
their disks, bootstraps Kubernetes, waits for all four nodes, installs MetalLB
and Traefik, deploys the demo, and verifies ingress HTTP. `up.sh` updates hosts
automatically when passwordless/cached sudo is available; otherwise it prints
the command to run. Terraform does not change your default kubeconfig.

Sizing, cluster name, subnet, versions, and hostname can be set in a
`terraform.tfvars` file; see `variables.tf`. CPU, memory, disk, subnet, or cluster
name changes replace VMs and their disks. For this single-control-plane lab,
rebuild the whole cluster for topology changes rather than replacing its sole
control plane while keeping old workers. Version variables select initial
installation and generated configuration; upgrading existing Talos or
Kubernetes requires the corresponding Talos upgrade procedure.

## Stop and start

```bash
./scripts/lab.sh stop     # Clean ACPI shutdown, retaining disks and state
./scripts/lab.sh start    # Start existing machines
./scripts/lab.sh status
```

Wait for shutdown to complete before starting again. Terraform apply does not
detect a manually stopped VM as drift; start existing machines with `lab.sh`.

## Remove

`terraform destroy` permanently deletes this lab's VMs, disks, network, and
credentials. It leaves other VMs and networks alone. Remove the marked
`devPlatform Talos lab` block from `/etc/hosts` afterwards if no longer needed.

## Troubleshooting

Provisioning log: `.runtime/apply.log`. VM serial logs:
`.runtime/talos-lab-*-serial.log`. Inspect VMs in VirtualBox or use:

```bash
./scripts/talosctl -n 192.168.57.10 services
./scripts/talosctl -n 192.168.57.10 logs kubelet
./scripts/kubectl get events -A --sort-by=.lastTimestamp
./scripts/kubectl -n metallb-system get pods
./scripts/kubectl -n traefik get service traefik
curl --noproxy '*' --resolve demo.talos.test:80:192.168.57.200 http://demo.talos.test
```

Sources: [Talos VirtualBox installation](https://docs.siderolabs.com/talos/v1.14/platform-specific-installations/local-platforms/virtualbox),
[Talos Terraform provider](https://registry.terraform.io/providers/siderolabs/talos/0.12.0/docs),
[MetalLB installation](https://metallb.io/installation/),
[Traefik Kubernetes setup](https://doc.traefik.io/traefik/setup/kubernetes/).

## Developer portal

Backstage is available at [http://demo.talos.test/backstage/](http://demo.talos.test/backstage/), with its own PostgreSQL database and the **Create FastAPI Microservice** template. See [portal setup](backstage/README.md) and [verification evidence](docs/backstage-proof.md). Install your GitHub App credentials locally with `python3 scripts/backstage-github-setup.py` to enable repository creation and protected GitOps onboarding PRs.
