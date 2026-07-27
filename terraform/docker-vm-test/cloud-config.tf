data "local_file" "ssh_public_key" {
  filename = "/Users/jon/.ssh/id_rsa.pub"
}

# NOTE: file_name differs from production on purpose. Identical names would
# overwrite the real snippets in local:snippets/ and break VM 201 on its next
# cloud-init run.
resource "proxmox_virtual_environment_file" "test_user_data" {
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
    # false here only to keep the test fast; production upgrades on first boot.
    package_upgrade: false
    packages:
      - qemu-guest-agent

    write_files:
      # Identical to production: docker must not start before its storage is
      # mounted, or every bind mount silently creates an empty directory.
      - path: /etc/systemd/system/docker.service.d/require-mounts.conf
        content: |
          [Unit]
          RequiresMountsFor=/mnt/main /mnt/appdata

    runcmd:
      - systemctl enable qemu-guest-agent
      - systemctl start qemu-guest-agent

      # --- storage (mirrors production) -------------------------------------
      - mkdir -p /mnt/appdata /mnt/main
      - blkid /dev/vdb || mkfs.ext4 -L appdata /dev/vdb
      - grep -q " /mnt/appdata " /etc/fstab || echo "LABEL=appdata /mnt/appdata ext4 defaults,nofail 0 2" >> /etc/fstab
      # tag is "maintest" here; production uses "main". The tag is the Proxmox
      # directory-mapping id in both cases.
      - grep -q " /mnt/main " /etc/fstab || echo "maintest /mnt/main virtiofs defaults,nofail 0 0" >> /etc/fstab
      - mount -a

      # Install docker so the mount guard is actually exercised.
      - DEBIAN_FRONTEND=noninteractive apt install -y ca-certificates curl
      - curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
      - echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
      - apt update
      - DEBIAN_FRONTEND=noninteractive apt install -y docker-ce
      - usermod -aG docker ubuntu
      - systemctl enable docker

      - echo "" > /home/ubuntu/init.done
      # Reboot so we verify the mounts and the guard survive a cold start,
      # which is the whole point of the exercise.
      - reboot
    EOF

    file_name = "test-user-data-cloud-config.yaml"
  }
}

resource "proxmox_virtual_environment_file" "test_meta_data" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = "homelab"

  source_raw {
    data = <<-EOF
    #cloud-config
    local-hostname: ubuntu-docker-test
    EOF

    file_name = "test-meta-data-cloud-config.yaml"
  }
}
