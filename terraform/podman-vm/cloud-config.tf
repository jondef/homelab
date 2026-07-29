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
      - podman
      - passt
      - uidmap
      - ranger

    write_files:
      # Rootless traefik must bind 80/443; default floor is 1024.
      - path: /etc/sysctl.d/50-unprivileged-ports.conf
        content: |
          net.ipv4.ip_unprivileged_port_start=80

      # Traefik holds its access log open (reached 4.7G unrotated on docker-1);
      # it reopens on USR1. Rootless: the signal goes through the user manager,
      # not a root docker daemon.
      - path: /etc/logrotate.d/traefik
        content: |
          /mnt/appdata/traefik/logs/access.log {
              daily
              rotate 14
              compress
              delaycompress
              missingok
              notifempty
              create 0644 ubuntu ubuntu
              sharedscripts
              postrotate
                  /usr/bin/systemctl --user -M ubuntu@ kill --signal=USR1 traefik >/dev/null 2>&1 || true
              endscript
          }

    runcmd:
      - systemctl enable qemu-guest-agent
      - systemctl start qemu-guest-agent
      - ufw disable

      # --- storage ---------------------------------------------------------
      # Same layout and lesson as docker-1. There is no daemon-level
      # RequiresMountsFor here: every quadlet unit declares it instead.
      - mkdir -p /mnt/appdata /mnt/main
      - blkid /dev/vdb || mkfs.ext4 -L appdata /dev/vdb
      - grep -q " /mnt/appdata " /etc/fstab || echo "LABEL=appdata /mnt/appdata ext4 defaults,nofail 0 2" >> /etc/fstab
      - grep -q " /mnt/main " /etc/fstab || echo "main /mnt/main virtiofs defaults,nofail 0 0" >> /etc/fstab
      - mount -a
      - chown ubuntu:ubuntu /mnt/appdata
      - sysctl --system

      # --- rootless podman -------------------------------------------------
      # Linger: the ubuntu user's systemd instance (and so every quadlet)
      # runs at boot with nobody logged in.
      - loginctl enable-linger ubuntu
      # Traefik's discovery endpoint: the docker-API-compatible user socket.
      - sudo -iu ubuntu XDG_RUNTIME_DIR=/run/user/1000 systemctl --user enable podman.socket
      - mkdir -p /home/ubuntu/.config/containers/systemd
      - chown -R ubuntu:ubuntu /home/ubuntu/.config

      - echo "" > /home/ubuntu/init.done
      - reboot
    EOF

    # NOT user-data-cloud-config.yaml: that name is docker-vm's snippet in the
    # same datastore - reusing it would overwrite docker-1's cloud-init.
    file_name = "podman-user-data-cloud-config.yaml"
  }
}

resource "proxmox_virtual_environment_file" "meta_data_cloud_config" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = "homelab"

  source_raw {
    data = <<-EOF
    #cloud-config
    local-hostname: ubuntu-podman
    EOF

    file_name = "podman-meta-data-cloud-config.yaml"
  }
}
