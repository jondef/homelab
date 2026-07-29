resource "proxmox_virtual_environment_vm" "podman_vm" {
  name      = "podman-1"
  vm_id     = 210
  node_name = "homelab"

  stop_on_destroy = true
  on_boot         = true
  tags            = ["external"]

  operating_system {
    type = "l26"
  }

  agent {
    enabled = true
  }

  cpu {
    # Starts modest next to docker-1's 16; rebalance as services migrate.
    cores = 8
    type  = "host"
  }

  machine = "q35"
  bios    = "ovmf"

  efi_disk {
    datastore_id = "local-zfs"
    type         = "4m"
  }

  memory {
    dedicated = 16384
    # Ballooning off for the same reason as docker-1: databases behave badly
    # when memory is reclaimed underneath them.
    floating = 0
  }

  # OS disk.
  disk {
    datastore_id = "local-zfs"
    file_id      = proxmox_virtual_environment_download_file.ubuntu_cloud_image.id
    interface    = "virtio0"
    iothread     = true
    discard      = "on"
    size         = 100
  }

  # Application state + databases, mounted at /mnt/appdata. Own zvol - ext4
  # cannot be shared between VMs; docker-1 keeps its own. Same mount point on
  # purpose so ${DOCKERDIR} and unit paths are identical across both VMs.
  disk {
    datastore_id = "local-zfs"
    interface    = "virtio1"
    iothread     = true
    discard      = "on"
    size         = 100
  }

  # Bulk data over virtiofs - the same host-side mapping docker-1 uses; a
  # directory mapping shares safely into multiple VMs. The mapping RESOURCE
  # lives in terraform/docker-vm/main.tf. ⚠️ Before docker-vm is ever
  # `terraform destroy`ed (decommission phase), `terraform state mv` that
  # resource here, or the mapping is destroyed under this VM.
  virtiofs {
    mapping      = "main"
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
        # Must stay <= .127: tailscale advertises /25 subnet routes, anything
        # above is unreachable remotely (see infrastructure.md).
        address = "192.168.1.110/24"
        gateway = "192.168.1.1"
      }
    }

    user_data_file_id = proxmox_virtual_environment_file.user_data_cloud_config.id
    meta_data_file_id = proxmox_virtual_environment_file.meta_data_cloud_config.id
  }
}

resource "proxmox_virtual_environment_download_file" "ubuntu_cloud_image" {
  content_type = "iso"
  datastore_id = "local"
  node_name    = "homelab"
  # 26.04 LTS: the only Ubuntu that is both LTS and ships podman 5.x (5.7.0)
  # in the stock repos - 24.04's podman 4.9 predates pasta source-IP
  # preservation and mature quadlets.
  url = "https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img"
}
