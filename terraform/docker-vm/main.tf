###########################################
#
# Add PCIe raw device with all functions:
# Intel Corporation HD Graphics 530
#
###########################################

resource "proxmox_virtual_environment_vm" "ubuntu_vm" {
  count = 1
  name = "docker-${count.index + 1}"
  vm_id = 201 + count.index
  node_name = "homelab"

  stop_on_destroy = true

  operating_system {
    type = "l26" # This sets the OS type to Linux 2.6/3.x/4.x/5.x/6.x kernel
  }

  agent {
    enabled = true
  }

  cpu {
    cores = 8
  }

  machine = "q35"
  bios    = "ovmf"

  efi_disk {
    datastore_id = "local-zfs"
    type         = "4m"  # Standard EFI partition size
  }

  memory {
    dedicated = 21000
  }

  disk {
    datastore_id = "local-zfs"
    file_id      = proxmox_virtual_environment_download_file.ubuntu_cloud_image.id
    interface    = "virtio0"
    iothread     = true
    discard      = "on"
    size         = 20
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
