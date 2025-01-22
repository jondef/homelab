if port 53 already occupied:
sudo lsof -i -P -n | grep LISTEN

systemctl disable systemd-resolved.service
systemctl stop systemd-resolved

'/etc/resolv.conf' with nameserver 8.8.8.8