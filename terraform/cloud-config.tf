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
      - apt-transport-https
      - ca-certificates
      - curl
      - gnupg
      - containerd
    write_files:
      - path: /etc/modules-load.d/k8s.conf
        content: |
          overlay
          br_netfilter
      - path: /etc/sysctl.d/k8s.conf
        content: |
          net.bridge.bridge-nf-call-iptables = 1
          net.ipv4.ip_forward = 1
          net.bridge.bridge-nf-call-ip6tables = 1
      - path: /etc/hosts
        append: true
        content: |
          192.168.1.100 k8s-master
          192.168.1.101 k8s-worker1

    runcmd:
      # Enable and start qemu-guest-agent
      - systemctl enable qemu-guest-agent
      - systemctl start qemu-guest-agent

      # Load kernel modules
      - modprobe overlay
      - modprobe br_netfilter
      - sysctl --system

      # Configure containerd
      - mkdir -p /etc/containerd
      - containerd config default | tee /etc/containerd/config.toml
      - sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
      - systemctl restart containerd

      # Add Kubernetes apt repository
      - curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
      - echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.32/deb/ /" | tee /etc/apt/sources.list.d/kubernetes.list

      # Install Kubernetes components
      - apt-get update
      - apt-get install -y kubelet kubeadm kubectl
      - apt-mark hold kubelet kubeadm kubectl

      # Disable swap
      - swapoff -a
      - sed -i '/swap/d' /etc/fstab

      # kubectl create deployment nginx-test --image=nginx:alpine
      # kubectl get pods -o wide
      # kubectl delete deployment nginx-test
      - if [ "$(hostname)" = "k8s-master" ]; then
          kubeadm init --pod-network-cidr=10.244.0.0/16 --node-name=k8s-master > /root/kubeadm-init.log 2>&1;
          mkdir -p /home/ubuntu/.kube;
          cp -i /etc/kubernetes/admin.conf /home/ubuntu/.kube/config;
          chown -R ubuntu:ubuntu /home/ubuntu/.kube;
          mkdir -p /root/.kube;
          cp -i /etc/kubernetes/admin.conf /root/.kube/config;
          su - ubuntu -c "kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml";
          kubeadm token create --print-join-command > /home/ubuntu/join-command.txt;
          echo "kubectl label node k8s-worker1 node-role.kubernetes.io/worker=" >> /home/ubuntu/join-command.txt
          chown ubuntu:ubuntu /home/ubuntu/join-command.txt;
          echo "kubernetes master setup complete" > /home/ubuntu/k8s-setup-master.done;
        else
          echo "kubernetes worker setup complete - ready for join command" > /home/ubuntu/k8s-setup-worker.done;
        fi

    EOF

    file_name = "user-data-cloud-config.yaml"
  }
}

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