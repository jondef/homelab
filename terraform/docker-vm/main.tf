###########################################
#
# Add PCIe raw device with all functions:
# Intel Corporation HD Graphics 530
#
###########################################

# Host directory exposed to guests over virtiofs. The host owns main_pool
# (2x20TB mirror, imported on the node - NOT passed through to a VM), so the
# bulk data outlives any VM that mounts it. The mapping *name* doubles as the
# virtiofs device tag the guest mounts, see cloud-config.tf.
resource "proxmox_hardware_mapping_dir" "main" {
  name    = "main"
  comment = "main_pool bulk storage (media, photos, nextcloud)"

  map = [
    {
      node = "homelab"
      path = "/mnt/main"
    },
  ]
}

resource "proxmox_virtual_environment_vm" "ubuntu_vm" {
  count = 1
  name = "docker-${count.index + 1}"
  vm_id = 201 + count.index
  node_name = "homelab"

  stop_on_destroy = true
  on_boot         = true
  tags            = ["external"]

  operating_system {
    type = "l26" # This sets the OS type to Linux 2.6/3.x/4.x/5.x/6.x kernel
  }

  agent {
    enabled = true
  }

  cpu {
    # Measured load is ~1.2 on this host; 16 leaves ~10x headroom for the
    # bursty work (immich ML, jellyfin transcode, latex). Giving it all 32
    # would let this guest contend with the host's own ZFS + virtiofsd.
    cores = 16
    type  = "host"
  }

  machine = "q35"
  bios    = "ovmf"

  efi_disk {
    datastore_id = "local-zfs"
    type         = "4m"  # Standard EFI partition size
  }

  memory {
    dedicated = 32768
    # Ballooning off: the ARC for main_pool now lives on the host, and
    # databases behave badly when memory is reclaimed underneath them.
    floating = 0
  }

  # OS disk.
  disk {
    datastore_id = "local-zfs"
    file_id      = proxmox_virtual_environment_download_file.ubuntu_cloud_image.id
    interface    = "virtio0"
    iothread     = true
    discard      = "on"
    size         = 200
  }

  # Application state + databases, mounted at /mnt/appdata.
  # A block device on NVMe, deliberately not a file share: databases need
  # low latency and real fsync. Measured 14634 file-creates/s here vs 561/s
  # over virtiofs.
  disk {
    datastore_id = "local-zfs"
    interface    = "virtio1"
    iothread     = true
    discard      = "on"
    size         = 100
  }

  # Bulk data (media, photos, nextcloud) from the host's HDD pool. Terraform
  # only attaches the device; the guest mounts it at /mnt/main via the fstab
  # entry in cloud-config.tf, using this mapping name as the virtiofs tag.
  virtiofs {
    mapping      = proxmox_hardware_mapping_dir.main.name
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
        #address = "dhcp"
        address = "192.168.1.${100 + count.index}/24"
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
  url          = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
}
