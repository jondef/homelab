# Proxmox host runbook

Situational recipes for the `homelab` node — **not** a script. Do not run
top-to-bottom: several sections reboot the host or are mutually exclusive.
Anything genuinely repeatable belongs in `terraform/` instead.

---

## Storage layout

Two pools, tiered by workload. The host owns **both** — no disk passthrough to
VMs, so storage outlives any VM that uses it.

| Pool | Devices | Holds |
|---|---|---|
| `rpool` | 2× NVMe mirror | VM disks (zvols), application state, databases |
| `main_pool` | 2× 20 TB mirror | bulk only — media, nextcloud, photos |

**Rule:** databases get a **block device** (a zvol attached as a virtual disk).
Bulk files get a **file share** (virtiofs). Never put a database behind a file
share — small fsync'd writes are its worst case.

---

## ZFS

### Import main_pool (host-owned, not passed through)

```bash
zpool import                                   # scan for importable pools
zpool import -d /dev/disk/by-id main_pool      # by-id survives device renaming
zfs list -r main_pool                          # main_pool/main_fs mounts at /mnt/main
strings /etc/zfs/zpool.cache | grep main_pool  # must appear, or it won't auto-import at boot
```

> A pool must only ever be imported in **one** place. Importing on the host
> while a VM still has the disks passed through will corrupt it.

### Cap the ARC

Defaults to 50% of RAM and will fight the VMs for memory.

```bash
echo "options zfs zfs_arc_max=34359738368" > /etc/modprobe.d/zfs.conf  # 32G, persistent
update-initramfs -u -k all                                             # bake into initramfs — required, see below
echo 34359738368 > /sys/module/zfs/parameters/zfs_arc_max              # runtime, no reboot
awk '/^size /{printf "%.1f GB\n", $3/1073741824}' /proc/spl/kstat/zfs/arcstats
```

With root on ZFS the module loads from the initramfs, which carries its own
copy of `zfs.conf` — editing the file alone does nothing after the next
reboot until the initramfs is rebuilt.

The pool's cache lives wherever the pool is imported. Moving a pool from a VM
to the host means moving that RAM budget too — shrink the VM by roughly what
you give the ARC.

### Grow a pool after replacing/expanding disks

```bash
zpool list -o name,size,free,expandsize       # EXPANDSZ = unclaimed space
zpool online -e rpool <dev-id-1> <dev-id-2>   # manual expand; autoexpand stays off
```

Metadata-only, non-destructive, online. Does **not** repartition — the ZFS
partition already spans the disk; this just tells ZFS to claim the rest.

---

## Share a host directory into a VM (virtiofs)

Replaces the old NFS export. Needs PVE ≥ 8.4.

```bash
pvesh create /cluster/mapping/dir --id main --map node=$(hostname),path=/mnt/main
cat /etc/pve/mapping/directory.cfg            # note: directory.cfg, not dir.cfg
qm set <vmid> --virtiofs0 dirid=main,cache=auto,expose-xattr=1
```

Needs a VM **stop/start** (not just a reboot) to attach.

In the guest, the "device" is the mapping id — the virtiofs tag — not a path:

```
# /etc/fstab
main /mnt/main virtiofs defaults,nofail 0 0
```

Both the mapping and the guest fstab entry are managed in
`terraform/docker-vm/` (`hardware_mapping_dir` + `cloud-config.tf`).

---

## Guest: stop Docker starting before its storage is mounted

Without this, Docker starts first, every bind mount silently creates an **empty
directory**, and the apps reinitialise into it. This has bitten this setup
twice — on 2026-05-29 it wrote 3.2 GB of shadow data onto the root filesystem,
invisible underneath the real mount.

```bash
mkdir -p /etc/systemd/system/docker.service.d
cat > /etc/systemd/system/docker.service.d/require-mounts.conf <<'EOF'
[Unit]
RequiresMountsFor=/mnt/main /mnt/appdata
EOF
systemctl daemon-reload
systemctl show docker.service -p RequiresMountsFor   # verify it took
```

---

## Why virtiofs and not NFS

Measured on this hardware (incompressible data, `compression=on` would fake it):

| | NVMe zvol | virtiofs | host native ZFS |
|---|---|---|---|
| seq write (fsync) | 448 MB/s | **129 MB/s** | **130 MB/s** |
| create 2000 files | 14634/s | 561/s | 6221/s |

- Sequential throughput over virtiofs is **free** — 129 vs 130 MB/s. The HDDs
  are the bottleneck, not the share. NFS typically loses 20–50% here.
- Metadata is ~11× slower than native. That is virtiofs' genuine weak spot,
  and exactly why databases live on the NVMe zvol instead.

<details>
<summary>Old NFS approach (superseded)</summary>

```bash
apt install nfs-kernel-server
# /etc/exports:  /mnt/main *(rw,sync,no_subtree_check)
exportfs -rav
# on the vm:
apt install nfs-common && mount <host>:/mnt/main /mnt/nfs
```
</details>

---

## Notifications (so disk failures actually reach you)

ZED emails `root` on pool events, and PVE mails root for backup/job failures.
By default that goes through local postfix — which on this host was broken in
two ways: `/etc/aliases.db` was never generated, and `relayhost` was empty, so
a real alert sat in the queue for **5 days and then expired undelivered**.

PVE 8+ routes notifications through its own system, which sidesteps postfix's
relay problem entirely. `/root/.forward` already pipes to
`proxmox-mail-forward`, so ZED alerts flow into the same path.

```bash
newaliases     # build /etc/aliases.db - postfix needs it or root won't resolve

pvesh create /cluster/notifications/endpoints/smtp \
  --name gmail --server smtp.gmail.com --port 465 --mode tls \
  --username <you>@gmail.com --password '<gmail APP password>' \
  --from-address <you>@gmail.com --mailto <you>@gmail.com

# the builtin matcher points at mail-to-root (local mail); repoint it
pvesh set /cluster/notifications/matchers/default-matcher --target gmail

pvesh create /cluster/notifications/targets/gmail/test   # verify, then check inbox
```

Gmail requires an **app password**, not the account password. The secret is
stored in `/etc/pve/priv/notifications.cfg`, not the world-readable one.

Check it still works occasionally — a silent notification path is worse than
none, because you believe you're covered.

---

## Container templates

```bash
pveam update
pveam available
pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst
```

---

## Maintenance

```bash
apt update && apt dist-upgrade        # update proxmox
iostat -dx 1                          # view disk io
```

Community scripts: <https://community-scripts.github.io/ProxmoxVE/scripts?id=microcode>

Remove the subscription nag:

```bash
wget https://raw.githubusercontent.com/foundObjects/pve-nag-buster/master/install.sh
bash install.sh
```

---

## Prepare Proxmox for Terraform

```bash
pveum role add TerraformRole -privs "Datastore.AllocateSpace Datastore.Allocate Datastore.AllocateTemplate Datastore.Audit VM.Allocate VM.Audit VM.Clone VM.Config.CDROM VM.Config.CPU VM.Config.Cloudinit VM.Config.Disk VM.Config.HWType VM.Config.Memory VM.Config.Network VM.Config.Options VM.Migrate VM.Monitor VM.PowerMgmt VM.GuestAgent.Audit Mapping.Audit Mapping.Modify Mapping.Use Sys.Audit Sys.Console Sys.Modify Pool.Allocate SDN.Use"

pveum role modify TerraformRole -privs <overwrite roles>

pveum user add terraform@pve
pveum aclmod / -user terraform@pve -role TerraformRole
pveum user token add terraform@pve terraform-token --privsep=0
```

`Mapping.*` is required for the `virtiofs` share — both to create the directory
mapping and to attach it to a VM. `VM.GuestAgent.Audit` lets terraform read the
VM's IPs back from the guest agent. Without them terraform **hangs rather than
erroring**, which is a miserable thing to debug:

```bash
# add to an existing role (note: -privs OVERWRITES, so pass the full list)
pveum role modify TerraformRole -privs "<existing>,Mapping.Audit,Mapping.Modify,Mapping.Use,VM.GuestAgent.Audit"
```

**Gotcha:** the bpg provider SSHes to the node by its *hostname*, which only
resolves on the home LAN. Running terraform from anywhere else (e.g. over
Tailscale) hangs with no error until it times out. Pin the address in the
provider's `ssh` block:

```hcl
ssh {
  node {
    name    = "homelab"
    address = "192.168.0.5"
  }
}
```

---

## Prepare Proxmox for GPU passthrough

### 1. Enable IOMMU

```bash
nano /etc/default/grub
# add to GRUB_CMDLINE_LINUX_DEFAULT:  "quiet intel_iommu=on iommu=pt"
update-grub
reboot
```

### 2. Load VFIO modules

```bash
echo 'vfio'             >> /etc/modules
echo 'vfio_iommu_type1' >> /etc/modules
echo 'vfio_pci'         >> /etc/modules
echo 'vfio_virqfd'      >> /etc/modules
update-initramfs -u
```

### 3. Get the GPU PCI ID

```bash
lspci -nn | grep VGA
ls /dev/dri/            # to test
```
