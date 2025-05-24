data "local_file" "ssh_public_key" {
  filename = "/Users/jon/.ssh/id_rsa.pub"
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
    write_files:
      - path: /etc/hosts
        append: true
        content: |
          192.168.1.100 k8s-master
          192.168.1.101 k8s-worker1

    runcmd:
      # Enable and start qemu-guest-agent
      - systemctl enable qemu-guest-agent
      - systemctl start qemu-guest-agent
      - ufw disable

      - if [ "$(hostname)" = "k8s-master" ]; then
          curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE=644 sh -;
          echo "curl -sfL https://get.k3s.io | K3S_URL=https://k8s-master:6443 K3S_TOKEN=$(cat /var/lib/rancher/k3s/server/node-token) sh -;" >> /home/ubuntu/join-command.txt;
          echo "kubectl label node k8s-worker1 node-role.kubernetes.io/worker=;" >> /home/ubuntu/join-command.txt;
          chown ubuntu:ubuntu /home/ubuntu/join-command.txt;
        else
          echo "kubernetes worker setup complete - ready for join command" > /home/ubuntu/k8s-setup-worker.done;
        fi
    EOF

    file_name = "user-data-cloud-config.yaml"
  }
}

#kubectl get nodes
#kubectl create deployment nginx-test --image=nginx:alpine
#kubectl scale deployment nginx-test --replicas=2
#kubectl get pods -o wide
#kubectl expose deployment nginx-test --type=NodePort --port=80 --target-port=80
#kubectl delete deployment nginx-test

resource "proxmox_virtual_environment_file" "meta_data_cloud_config_master" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = "homelab"

  source_raw {
    data = <<-EOF
    #cloud-config
    local-hostname: k8s-master
    EOF

    file_name = "meta-data-cloud-config-master.yaml"
  }
}

resource "proxmox_virtual_environment_file" "meta_data_cloud_config_worker1" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = "homelab"

  source_raw {
    data = <<-EOF
    #cloud-config
    local-hostname: k8s-worker1
    EOF

    file_name = "meta-data-cloud-config-worker1.yaml"
  }
}