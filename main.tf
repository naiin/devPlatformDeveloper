locals {
  root       = abspath(path.module)
  runtime    = "${local.root}/.runtime"
  subnet     = "${var.network_prefix}.0/24"
  cp_ip      = "${var.network_prefix}.10"
  ingress_ip = "${var.network_prefix}.200"
  # Empty official Image Factory schematic, paired with the stock metal ISO.
  schematic = "376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba"
  nodes = {
    cp1     = { type = "controlplane", ip = local.cp_ip, mac = "080027570010" }
    worker1 = { type = "worker", ip = "${var.network_prefix}.11", mac = "080027570011" }
    worker2 = { type = "worker", ip = "${var.network_prefix}.12", mac = "080027570012" }
    worker3 = { type = "worker", ip = "${var.network_prefix}.13", mac = "080027570013" }
  }
}

resource "terraform_data" "image" {
  input = {
    root               = local.root
    version            = var.talos_version
    kubernetes_version = var.kubernetes_version
  }
  triggers_replace = [var.talos_version, var.kubernetes_version]
  provisioner "local-exec" {
    command     = "bash scripts/download.sh"
    working_dir = self.input.root
    environment = {
      TALOS_VERSION      = self.input.version
      KUBERNETES_VERSION = self.input.kubernetes_version
    }
  }
}

# VBoxManage manages the VM lifecycle; the official siderolabs/talos provider
# manages secrets, machine configuration, bootstrap, and Kubernetes credentials.
resource "terraform_data" "network" {
  input = {
    root   = local.root
    prefix = var.network_prefix
  }
  triggers_replace = [var.network_prefix]
  provisioner "local-exec" {
    command     = "python3 scripts/vbox.py network-create"
    working_dir = self.input.root
    environment = { INPUT_JSON = jsonencode(self.input) }
  }
  provisioner "local-exec" {
    when        = destroy
    command     = "python3 scripts/vbox.py network-delete"
    working_dir = self.input.root
    environment = { INPUT_JSON = jsonencode(self.input) }
  }
}

resource "terraform_data" "vm" {
  for_each = local.nodes
  input = {
    root             = local.root
    prefix           = var.network_prefix
    name             = "${var.cluster_name}-${each.key}"
    ip               = each.value.ip
    mac              = each.value.mac
    memory           = var.node_memory_mb
    cpus             = var.node_cpus
    disk_size        = var.disk_size_mb
    talos_version    = var.talos_version
    bridge_interface = var.bridge_interface
  }
  triggers_replace = [
    var.cluster_name, each.value.ip, var.node_memory_mb, var.node_cpus,
    var.disk_size_mb, terraform_data.network.id
  ]
  depends_on = [terraform_data.image, terraform_data.network]
  provisioner "local-exec" {
    command     = "python3 scripts/vbox.py create"
    working_dir = self.input.root
    environment = { INPUT_JSON = jsonencode(self.input) }
  }
  provisioner "local-exec" {
    when        = destroy
    command     = "python3 scripts/vbox.py delete"
    working_dir = self.input.root
    environment = { INPUT_JSON = jsonencode(self.input) }
  }
}

resource "terraform_data" "uplink" {
  for_each = local.nodes
  input = {
    root             = local.root
    name             = "${var.cluster_name}-${each.key}"
    bridge_interface = var.bridge_interface
  }
  triggers_replace = [terraform_data.vm[each.key].id, var.bridge_interface]
  provisioner "local-exec" {
    command     = "python3 scripts/vbox.py uplink"
    working_dir = self.input.root
    environment = { INPUT_JSON = jsonencode(self.input) }
  }
}

resource "talos_machine_secrets" "cluster" {
  talos_version = var.talos_version
}

data "talos_machine_configuration" "node" {
  for_each           = local.nodes
  cluster_name       = var.cluster_name
  cluster_endpoint   = "https://${local.cp_ip}:6443"
  machine_type       = each.value.type
  machine_secrets    = talos_machine_secrets.cluster.machine_secrets
  talos_version      = var.talos_version
  kubernetes_version = var.kubernetes_version
  # Talos 1.14 generates separate documents for installation, hostname,
  # networking, and Kubernetes settings. Patch those documents directly.
  config_patches = concat([
    yamlencode({
      apiVersion = "v1alpha1"
      kind       = "UnattendedInstallConfig"
      installer  = { image = "factory.talos.dev/metal-installer/${local.schematic}:${var.talos_version}" }
      provisioning = {
        diskSelector = { match = "disk.dev_path == \"/dev/sda\"" }
        wipe         = false
      }
    }),
    yamlencode({
      apiVersion = "v1alpha1"
      kind       = "HostnameConfig"
      auto       = "off"
      hostname   = "${var.cluster_name}-${each.key}"
    }),
    yamlencode({
      apiVersion = "v1alpha1"
      kind       = "LinkConfig"
      name       = "enp0s3"
      addresses  = [{ address = "${each.value.ip}/24" }]
    }),
    yamlencode({
      apiVersion     = "v1alpha1"
      kind           = "DHCPv4Config"
      name           = "enp0s8"
      ignoreHostname = true
    }),
    yamlencode({
      apiVersion  = "v1alpha1"
      kind        = "ResolverConfig"
      nameservers = [for address in var.dns_servers : { address = address }]
    }),
    yamlencode({
      apiVersion = "v1alpha1"
      kind       = "KubeNodeConfig"
      nodeIP     = { validSubnets = [local.subnet] }
    }),
    yamlencode({
      apiVersion     = "v1alpha1"
      kind           = "KubeNetworkConfig"
      podSubnets     = ["10.244.0.0/16"]
      serviceSubnets = ["10.96.0.0/12"]
    })
    ], each.value.type == "controlplane" ? [yamlencode({
      cluster = { etcd = { advertisedSubnets = [local.subnet] } }
  })] : [])
}

resource "talos_machine_configuration_apply" "node" {
  for_each                    = local.nodes
  node                        = each.value.ip
  endpoint                    = each.value.ip
  client_configuration        = talos_machine_secrets.cluster.client_configuration
  machine_configuration_input = data.talos_machine_configuration.node[each.key].machine_configuration
  depends_on                  = [terraform_data.uplink]
  lifecycle {
    replace_triggered_by = [terraform_data.vm[each.key].id]
  }
  timeouts = { create = "15m", update = "15m" }
}

resource "talos_machine_bootstrap" "cluster" {
  node                 = local.cp_ip
  endpoint             = local.cp_ip
  client_configuration = talos_machine_secrets.cluster.client_configuration
  depends_on           = [talos_machine_configuration_apply.node]
  lifecycle {
    replace_triggered_by = [terraform_data.vm["cp1"].id]
  }
  timeouts = { create = "15m" }
}

data "talos_client_configuration" "cluster" {
  cluster_name         = var.cluster_name
  client_configuration = talos_machine_secrets.cluster.client_configuration
  endpoints            = [local.cp_ip]
  nodes                = [local.cp_ip]
}

resource "local_sensitive_file" "talosconfig" {
  filename             = "${local.root}/generated/talosconfig"
  content              = data.talos_client_configuration.cluster.talos_config
  file_permission      = "0600"
  directory_permission = "0700"
}

resource "talos_cluster_kubeconfig" "cluster" {
  node                 = local.cp_ip
  endpoint             = local.cp_ip
  client_configuration = talos_machine_secrets.cluster.client_configuration
  depends_on           = [talos_machine_bootstrap.cluster]
}

resource "local_sensitive_file" "kubeconfig" {
  filename             = "${local.root}/generated/kubeconfig"
  content              = talos_cluster_kubeconfig.cluster.kubeconfig_raw
  file_permission      = "0600"
  directory_permission = "0700"
}

resource "terraform_data" "addons" {
  input = {
    root       = local.root
    ingress_ip = local.ingress_ip
    hostname   = var.demo_hostname
  }
  triggers_replace = [
    talos_machine_bootstrap.cluster.id,
    sha256(local_sensitive_file.kubeconfig.content),
    filesha256("${path.module}/scripts/addons.sh"),
    filesha256("${path.module}/manifests/demo.yaml"),
    filesha256("${path.module}/manifests/traefik-values.yaml"),
    local.ingress_ip, var.demo_hostname
  ]
  depends_on = [local_sensitive_file.kubeconfig, talos_machine_configuration_apply.node]
  provisioner "local-exec" {
    command     = "bash scripts/addons.sh"
    working_dir = self.input.root
    environment = {
      INGRESS_IP    = self.input.ingress_ip
      DEMO_HOSTNAME = self.input.hostname
      KUBECONFIG    = "${self.input.root}/generated/kubeconfig"
    }
  }
}

