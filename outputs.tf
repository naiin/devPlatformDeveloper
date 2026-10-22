output "nodes" {
  value = { for key, node in local.nodes : "${var.cluster_name}-${key}" => node.ip }
}
output "demo_url" {
  value = "http://${var.demo_hostname}"
}
output "ingress_ip" {
  value = local.ingress_ip
}
output "kubeconfig" {
  value = local_sensitive_file.kubeconfig.filename
}
output "talosconfig" {
  value = local_sensitive_file.talosconfig.filename
}
output "talos_version" {
  value = var.talos_version
}

