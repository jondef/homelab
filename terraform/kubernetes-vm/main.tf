resource "proxmox_virtual_environment_vm" "ubuntu_vm" {
  count = 1
  name = "kubernetes-${count.index + 1}"
  #id = count.index + 50
  node_name = "homelab"

  stop_on_destroy = true

  agent {
    enabled = true
  }

  cpu {
    cores = 2
  }

  memory {
    dedicated = 4096
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
    meta_data_file_id = count.index == 0 ? proxmox_virtual_environment_file.meta_data_cloud_config_master.id : proxmox_virtual_environment_file.meta_data_cloud_config_worker1.id

  }

}

resource "proxmox_virtual_environment_download_file" "ubuntu_cloud_image" {
  content_type = "iso"
  datastore_id = "local"
  node_name    = "homelab"
  url          = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
}
