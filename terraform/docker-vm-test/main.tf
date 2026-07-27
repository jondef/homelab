###########################################
#
# THROWAWAY VM - verifies that the docker-vm config can build from cold.
#
# Deliberately isolated from production so it can never touch VM 201:
#   - its own state directory
#   - vm_id 210 / 192.168.1.110 (docker-1 is 201 / .100)
#   - its own cloud-init snippet filenames (identical names would overwrite
#     the production snippets in local:snippets/)
#   - its own directory mapping pointing at a scratch dir, so the guest
#     cannot reach the 2TB of real data on main_pool
#
# Destroy with `terraform destroy` when finished.
#
###########################################

# Exercises the same resource type production uses, against a scratch path.
resource "proxmox_hardware_mapping_dir" "maintest" {
  name    = "maintest"
  comment = "scratch share for terraform build test - safe to delete"

  map = [
    {
      node = "homelab"
      path = "/mnt/main/.tftest"
    },
  ]
}

resource "proxmox_virtual_environment_vm" "test_vm" {
  name      = "docker-test"
  vm_id     = 210
  node_name = "homelab"

  stop_on_destroy = true
  on_boot         = false
  tags            = ["test", "ephemeral"]

  operating_system {
    type = "l26"
  }

  agent {
    enabled = true
  }

  # Scaled down - we are testing the shape of the config, not capacity.
  cpu {
    cores = 2
    type  = "host"
  }

  machine = "q35"
  bios    = "ovmf"

  efi_disk {
    datastore_id = "local-zfs"
    type         = "4m"
  }

  memory {
    dedicated = 2048
    floating  = 0
  }

  # Reuses the image the production config already downloaded, rather than
  # managing (and re-downloading) it here.
  disk {
    datastore_id = "local-zfs"
    file_id      = "local:iso/jammy-server-cloudimg-amd64.img"
    interface    = "virtio0"
    iothread     = true
    discard      = "on"
    size         = 20
  }

  # Stands in for the production /mnt/appdata disk. cloud-init should mkfs
  # and mount this - that is one of the things under test.
  disk {
    datastore_id = "local-zfs"
    interface    = "virtio1"
    iothread     = true
    discard      = "on"
    size         = 5
  }

  virtiofs {
    mapping      = proxmox_hardware_mapping_dir.maintest.name
    cache        = "auto"
    expose_xattr = true
  }

  network_device {
    bridge = "vmbr1"
  }

  initialization {
    datastore_id = "local-zfs"

    ip_config {
      ipv4 {
        address = "192.168.1.110/24"
        gateway = "192.168.1.1"
      }
    }

    user_data_file_id = proxmox_virtual_environment_file.test_user_data.id
    meta_data_file_id = proxmox_virtual_environment_file.test_meta_data.id
  }
}

output "verify" {
  value = <<-EOT
    ssh ubuntu@192.168.1.110 'mount | grep -E "/mnt/(main|appdata)"; systemctl show docker -p RequiresMountsFor; cat /mnt/main/marker.txt'
  EOT
}
