# export TF_LOG=TRACE

terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

provider "proxmox" {
  endpoint = var.virtual_environment_endpoint
  api_token = "${var.virtual_environment_username}!${var.token_id}=${var.token_secret}"
  insecure = true
  ssh {
    agent = true
    username = "root"
    private_key = file("~/.ssh/id_rsa")
  }
}
