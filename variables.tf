variable "cluster_name" {
  type    = string
  default = "talos-lab"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,30}$", var.cluster_name))
    error_message = "Use a short lowercase cluster name."
  }
}

variable "talos_version" {
  type    = string
  default = "v1.14.4"
}

variable "kubernetes_version" {
  type    = string
  default = "1.37.1"
}

variable "network_prefix" {
  description = "Dedicated /24 host-only subnet. VirtualBox permits 192.168.56.0/21 by default."
  type        = string
  default     = "192.168.57"
  validation {
    condition     = can(regex("^192\\.168\\.(5[6-9]|6[0-3])$", var.network_prefix))
    error_message = "Choose 192.168.56 through 192.168.63, avoiding existing host networks."
  }
}

variable "node_memory_mb" {
  type    = number
  default = 3072
  validation {
    condition     = var.node_memory_mb >= 2048 && var.node_memory_mb <= 4096
    error_message = "Choose 2048–4096 MiB per VM for this 31 GiB workstation."
  }
}

variable "node_cpus" {
  type    = number
  default = 2
}

variable "disk_size_mb" {
  description = "Dynamically allocated VDI size per node."
  type        = number
  default     = 40960
}

variable "dns_servers" {
  description = "Explicit guest DNS servers."
  type        = list(string)
  default     = ["1.1.1.1", "1.0.0.1"]
}

variable "bridge_interface" {
  description = "Physical Ubuntu interface used for guest internet access; the cluster stays on its host-only NIC."
  type        = string
  default     = "wlp0s20f3"
}

variable "demo_hostname" {
  type    = string
  default = "demo.talos.test"
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]*\\.test$", var.demo_hostname))
    error_message = "Use a local .test hostname."
  }
}

