data "local_file" "ssh_public_key" {
  filename = pathexpand(var.ssh_public_key_path)
}

resource "proxmox_virtual_environment_file" "user_data_cloud_config" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = "homelab"

  source_raw {
    data = <<-EOF
    #cloud-config
    timezone: Europe/Zurich
    users:
      - default
      - name: ubuntu
        groups:
          - sudo
        shell: /bin/bash
        ssh_authorized_keys:
          - ${trimspace(data.local_file.ssh_public_key.content)}
        sudo: ALL=(ALL) NOPASSWD:ALL
    package_update: true
    package_upgrade: true
    packages:
      - qemu-guest-agent
      - nfs-common
      - ranger

    write_files:
      # Docker must not start before its storage is mounted. Without this every
      # bind mount silently creates an empty directory and the apps reinitialise
      # into it - that wrote 3.2G of shadow data to the root fs on 2026-05-29.
      - path: /etc/systemd/system/docker.service.d/require-mounts.conf
        content: |
          [Unit]
          RequiresMountsFor=/mnt/main /mnt/appdata

      # Traefik logs to stdout; docker's 'local' logging driver (set in the
      # compose file) handles rotation. The earlier logrotate + USR1-kill setup
      # was removed 2026-07-31: the daily `docker kill --signal=USR1` stopped
      # the container's restart-manager, which is the likely reason traefik
      # alone was not auto-restarted after that evening's power loss.

    runcmd:
      # Enable and start qemu-guest-agent
      - systemctl enable qemu-guest-agent
      - systemctl start qemu-guest-agent
      - ufw disable

      # --- storage ---------------------------------------------------------
      # virtio1 (/dev/vdb) holds application state and databases. It is a block
      # device rather than a share on purpose: databases need low latency and a
      # real fsync. Measured 14634 file-creates/s here vs 561/s over virtiofs.
      - mkdir -p /mnt/appdata /mnt/main
      - blkid /dev/vdb || mkfs.ext4 -L appdata /dev/vdb
      - grep -q " /mnt/appdata " /etc/fstab || echo "LABEL=appdata /mnt/appdata ext4 defaults,nofail 0 2" >> /etc/fstab
      # Bulk data shared from the host's HDD pool. The "device" here is the
      # Proxmox directory-mapping id (the virtiofs tag), not a path.
      - grep -q " /mnt/main " /etc/fstab || echo "main /mnt/main virtiofs defaults,nofail 0 0" >> /etc/fstab
      - mount -a

      # Install docker engine
      - DEBIAN_FRONTEND=noninteractive apt install -y apt-transport-https ca-certificates curl software-properties-common
      - curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
      - echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list
      - apt update
      - apt install -y docker-ce
      - usermod -aG docker ubuntu
      - systemctl enable docker

      # install pkgs for gpu passthrough - THIS APT IS NOT WORKING
      #- DEBIAN_FRONTEND=noninteractive apt install -y linux-modules-extra-`uname -r`
      #- modprobe i915

      - echo "" > /home/ubuntu/init.done
      - reboot
    EOF

    file_name = "user-data-cloud-config.yaml"
  }
}

resource "proxmox_virtual_environment_file" "meta_data_cloud_config" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = "homelab"

  source_raw {
    data = <<-EOF
    #cloud-config
    local-hostname: ubuntu-docker
    EOF

    file_name = "meta-data-cloud-config.yaml"
  }
}
