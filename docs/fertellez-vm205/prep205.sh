#!/bin/bash
# Turns the fresh clone of VM 204 (velacasa) into VM 205 (fertellez). Run ONCE as root inside the VM while its NIC is
# link-down (qm set 205 --net0 ...,link_down=1), so the clone never appears on the network with velacasa's identity.
# Mirrors what /root/prep204.sh did for VM 204 (homelab docs/velacasa-staging-vm204.md).
#   qm guest exec 205 -- bash -c "$(cat prep205.sh)"      # from the Proxmox host, with the three files in /root
# Expects fertellez-port-guard and fertellez-port-guard.service next to this script (or already in /root).
set -euo pipefail
NEW_HOST=fertellez
NEW_IP=192.168.1.105
OLD_IP=192.168.1.104
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "1/6 velacasa stack, images and volumes"
systemctl disable --now velacasa-port-guard.service 2>/dev/null || true
rm -f /etc/systemd/system/velacasa-port-guard.service /usr/local/sbin/velacasa-port-guard
systemctl daemon-reload
docker ps -aq | xargs -r docker rm -f
docker system prune -a --volumes -f
rm -rf /home/jon/mercantus-airbnb /home/jon/build-warm.log /home/jon/.deploy

echo "2/6 hostname"
hostnamectl set-hostname "$NEW_HOST"
sed -i "s/\bvelacasa\b/$NEW_HOST/g" /etc/hosts

echo "3/6 static address $NEW_IP"
sed -i "s/$OLD_IP/$NEW_IP/g" /etc/netplan/01-static.yaml
netplan generate

echo "4/6 new machine-id and SSH host keys"
rm -f /etc/machine-id /var/lib/dbus/machine-id
systemd-machine-id-setup
cp /etc/machine-id /var/lib/dbus/machine-id
rm -f /etc/ssh/ssh_host_*
ssh-keygen -A
systemctl restart ssh

echo "5/6 port guard for 3000 (docker-1 only)"
install -m 755 "$HERE/fertellez-port-guard" /usr/local/sbin/fertellez-port-guard
install -m 644 "$HERE/fertellez-port-guard.service" /etc/systemd/system/fertellez-port-guard.service
systemctl daemon-reload
systemctl enable --now fertellez-port-guard.service

echo "6/6 done: bring the link up (qm set 205 --net0 virtio=<MAC>,bridge=vmbr1,firewall=1) and reboot once"
