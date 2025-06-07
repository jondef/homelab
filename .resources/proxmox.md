pveam update
pveam available
pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst

# to setup zfs and nfs
zpool import # to scan for imports available
zpool import main_pool # should be automatically mounted
apt install nfs-kernel-server
vi /etc/exports
- add: /mnt/main *(rw,sync,no_subtree_check)
systemctl start nfs-kernel-server
systemctl enable nfs-kernel-server
exportfs -rav

- on vm:
sudo apt update
sudo apt install nfs-common
sudo mount <Proxmox_IP>:/mnt/main /mnt/nfs


# To update proxmox:
apt update && apt dist-upgrade

# Custom scripts
https://community-scripts.github.io/ProxmoxVE/scripts?id=microcode

# View disk io
iostat -dx 1

# To remove subscription nag:
wget https://raw.githubusercontent.com/foundObjects/pve-nag-buster/master/install.sh
bash install.sh


# prepare proxmox for terraform
pveum role add TerraformRole -privs "Datastore.AllocateSpace Datastore.Allocate Datastore.AllocateTemplate Datastore.Audit VM.Allocate VM.Audit VM.Clone VM.Config.CDROM VM.Config.CPU VM.Config.Cloudinit VM.Config.Disk VM.Config.HWType VM.Config.Memory VM.Config.Network VM.Config.Options VM.Migrate VM.Monitor VM.PowerMgmt Sys.Audit Sys.Console Sys.Modify Pool.Allocate SDN.Use"

pveum role modify TerraformRole -privs <overwrite roles>

pveum user add terraform@pve
pveum aclmod / -user terraform@pve -role TerraformRole
pveum user token add terraform@pve terraform-token --privsep=0


# prepare proxmox for gpu passthrough
### 1. Enable IOMMU and GPU passthrough
nano /etc/default/grub                              # Edit GRUB config
### Add to GRUB_CMDLINE_LINUX_DEFAULT:
###   "quiet intel_iommu=on iommu=pt"
update-grub                                         # Apply GRUB changes
reboot                                              # Reboot host

### 2. Load VFIO modules
echo 'vfio' >> /etc/modules
echo 'vfio_iommu_type1' >> /etc/modules
echo 'vfio_pci' >> /etc/modules
echo 'vfio_virqfd' >> /etc/modules
update-initramfs -u                                 # Update initramfs

### 3. Get GPU PCI ID
lspci -nn | grep VGA

### to test
ls /dev/dri/


# setup tailscale to work with inet GL-3000
tailscale up --exit-node=<homelab_tailscale_ip> --accept-dns=false --accept-routes --advertise-routes=192.168.10.0/24