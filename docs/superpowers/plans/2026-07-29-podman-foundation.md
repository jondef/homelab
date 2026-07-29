# Podman Foundation Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a rootless-podman VM (podman-1) as the homelab's new front door — traefik, authelia and a whoami pilot as quadlets — with TLS passthrough back to docker-1 for every un-migrated service.

**Architecture:** A new `terraform/podman-vm/` provisions Ubuntu 26.04 with podman 5.7, rootless under the `ubuntu` user. Quadlet unit files live in `podman/` in this repo and are synced to `~/.config/containers/systemd/` by a new podman dispatch path in `manage.py`. The OPNsense 80/443 port forward flips from 192.168.1.100 to 192.168.1.110 once the chain is verified; rollback is flipping it back.

**Tech Stack:** Terraform (bpg/proxmox), cloud-init, podman 5.7 quadlets, systemd user manager, traefik 3.7, authelia 4.

**Spec:** `docs/superpowers/specs/2026-07-29-podman-foundation-design.md`

## Global Constraints

- Podman version must be ≥ 5.x (pasta source-IP preservation, mature quadlets) — Ubuntu 26.04 ships 5.7.0, no third-party repos.
- podman-1: VM id **210**, IP **192.168.1.110/24** — must stay ≤ .127 (tailscale advertises /25 routes; anything above is invisible remotely).
- Mount points identical to docker-1: `/mnt/appdata` (own 100 GB zvol, ext4) and `/mnt/main` (shared virtiofs mapping `main`).
- Everything rootless under the `ubuntu` user (uid 1000). No per-service users. No docker on this VM.
- Every `.container` unit: `RequiresMountsFor=/mnt/main /mnt/appdata` in `[Unit]` (shadow-data lesson), `AutoUpdate=registry`, `[Install] WantedBy=default.target`.
- Podman networks allocate from 10.88.0.0/16 — must never land in `192.168.x` (new invariant, same spirit as docker's `172.x` rule).
- Nothing on docker-1 is removed in this phase. Authelia is *stopped* there, not deleted.
- The cloud-init snippet **file names must differ from docker-vm's** (`user-data-cloud-config.yaml` / `meta-data-cloud-config.yaml` live in the same Proxmox `local` datastore — reusing the names overwrites docker-1's snippets).
- The `proxmox_hardware_mapping_dir.main` resource stays in docker-vm's state; podman-vm references the mapping by name string only.
- The public domain is written literally in `dynamic/legacy-docker1.yml` (it is already public in `.resources/infrastructure.md`); everywhere else use `${HOST_DOMAIN}`-style expansion from `.env`. Where this plan writes `mercantus.ch`, confirm it matches `HOST_DOMAIN` in `.env` first.
- Work happens on this machine (LAN), committed to master and pushed; the VM pulls from origin. SSH targets: `ubuntu@192.168.1.110` (podman-1), `ubuntu@192.168.1.100` (docker-1).

---

### Task 1: Terraform for podman-1

**Files:**
- Create: `terraform/podman-vm/provider.tf`
- Create: `terraform/podman-vm/variables.tf`
- Create: `terraform/podman-vm/main.tf`
- Create: `terraform/podman-vm/cloud-config.tf`
- Copy (not committed if gitignored): `terraform/podman-vm/terraform.tfvars` from `terraform/docker-vm/terraform.tfvars`

**Interfaces:**
- Consumes: the existing Proxmox directory mapping named `main` (owned by docker-vm's state).
- Produces: a running VM `podman-1` at 192.168.1.110 with rootless podman 5.7, linger for `ubuntu`, user podman.socket enabled, `/mnt/appdata` + `/mnt/main` mounted, unprivileged ports ≥ 80, traefik logrotate installed. All later tasks SSH into it.

- [ ] **Step 1: Copy provider.tf and variables.tf verbatim from docker-vm**

```bash
mkdir -p terraform/podman-vm
cp terraform/docker-vm/provider.tf terraform/podman-vm/provider.tf
cp terraform/docker-vm/variables.tf terraform/podman-vm/variables.tf
cp terraform/docker-vm/terraform.tfvars terraform/podman-vm/terraform.tfvars
```

These files are identical by design (same node, same token, same SSH pinning to 192.168.0.5).

- [ ] **Step 2: Write `terraform/podman-vm/main.tf`**

```hcl
resource "proxmox_virtual_environment_vm" "podman_vm" {
  name      = "podman-1"
  vm_id     = 210
  node_name = "homelab"

  stop_on_destroy = true
  on_boot         = true
  tags            = ["external"]

  operating_system {
    type = "l26"
  }

  agent {
    enabled = true
  }

  cpu {
    # Starts modest next to docker-1's 16; rebalance as services migrate.
    cores = 8
    type  = "host"
  }

  machine = "q35"
  bios    = "ovmf"

  efi_disk {
    datastore_id = "local-zfs"
    type         = "4m"
  }

  memory {
    dedicated = 16384
    # Ballooning off for the same reason as docker-1: databases behave badly
    # when memory is reclaimed underneath them.
    floating = 0
  }

  # OS disk.
  disk {
    datastore_id = "local-zfs"
    file_id      = proxmox_virtual_environment_download_file.ubuntu_cloud_image.id
    interface    = "virtio0"
    iothread     = true
    discard      = "on"
    size         = 100
  }

  # Application state + databases, mounted at /mnt/appdata. Own zvol - ext4
  # cannot be shared between VMs; docker-1 keeps its own. Same mount point on
  # purpose so ${DOCKERDIR} and unit paths are identical across both VMs.
  disk {
    datastore_id = "local-zfs"
    interface    = "virtio1"
    iothread     = true
    discard      = "on"
    size         = 100
  }

  # Bulk data over virtiofs - the same host-side mapping docker-1 uses; a
  # directory mapping shares safely into multiple VMs. The mapping RESOURCE
  # lives in terraform/docker-vm/main.tf. ⚠️ Before docker-vm is ever
  # `terraform destroy`ed (decommission phase), `terraform state mv` that
  # resource here, or the mapping is destroyed under this VM.
  virtiofs {
    mapping      = "main"
    cache        = "auto"
    expose_xattr = true
  }

  network_device {
    bridge = "vmbr1"
  }

  initialization {
    datastore_id = "local-zfs"

    ip_config {
      ipv4 {
        # Must stay <= .127: tailscale advertises /25 subnet routes, anything
        # above is unreachable remotely (see infrastructure.md).
        address = "192.168.1.110/24"
        gateway = "192.168.1.1"
      }
    }

    user_data_file_id = proxmox_virtual_environment_file.user_data_cloud_config.id
    meta_data_file_id = proxmox_virtual_environment_file.meta_data_cloud_config.id
  }
}

resource "proxmox_virtual_environment_download_file" "ubuntu_cloud_image" {
  content_type = "iso"
  datastore_id = "local"
  node_name    = "homelab"
  # 26.04 LTS: the only Ubuntu that is both LTS and ships podman 5.x (5.7.0)
  # in the stock repos - 24.04's podman 4.9 predates pasta source-IP
  # preservation and mature quadlets.
  url = "https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img"
}
```

- [ ] **Step 3: Write `terraform/podman-vm/cloud-config.tf`**

```hcl
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
```

- [ ] **Step 4: Init and plan**

```bash
cd terraform/podman-vm && terraform init && terraform plan
```

Expected: plan creates exactly 4 resources (VM, image download, 2 snippet files). It must NOT touch the hardware mapping or anything in docker-vm's state. If the plan wants to create a `proxmox_hardware_mapping_dir`, stop — `mapping = "main"` must be a plain string reference.

- [ ] **Step 5: Apply and wait for first boot + the cloud-init reboot**

```bash
terraform apply
```

Cloud-init ends with a reboot; give it ~3–5 minutes after apply completes.

- [ ] **Step 6: Verify the VM**

```bash
ssh ubuntu@192.168.1.110 '
  podman --version &&
  findmnt /mnt/appdata /mnt/main &&
  sysctl net.ipv4.ip_unprivileged_port_start &&
  loginctl show-user ubuntu -p Linger &&
  systemctl --user is-enabled podman.socket &&
  ls -d ~/.config/containers/systemd &&
  test -f ~/init.done && echo CLOUD-INIT-DONE'
```

Expected: `podman version 5.7.x`; both mounts present (appdata ext4, main virtiofs); `net.ipv4.ip_unprivileged_port_start = 80`; `Linger=yes`; `enabled`; the quadlet dir exists; `CLOUD-INIT-DONE`.

- [ ] **Step 7: Commit**

```bash
git add terraform/podman-vm/provider.tf terraform/podman-vm/variables.tf terraform/podman-vm/main.tf terraform/podman-vm/cloud-config.tf
git commit -m "Provision podman-1: ubuntu 26.04, rootless podman 5.7"
git push
```

(Confirm `terraform.tfvars` and state files are covered by the existing `.gitignore` before pushing — check with `git status`; they hold the Proxmox token.)

---

### Task 2: manage.py learns podman/quadlets

**Files:**
- Modify: `manage.py`
- Create: `tests/test_manage.py`

**Interfaces:**
- Consumes: repo layout convention `podman/{infrastructure,services}/<name>/*.{container,network,volume,pod}` and optional `<name>/dynamic/*.yml`.
- Produces: `PodmanQuadletManager` with methods `get_service_path(service)`, `unit_files(service)`, `container_units(service)` (returns e.g. `["traefik.service"]`), `sync(service)`, `start_service`, `stop_service`, `restart_service`, `update_service`, `show_logs`, `show_status`, `is_service_running`; module-level `parse_env(path) -> dict`. `main()` dispatches per service to docker or podman manager. Later tasks run `python3 manage.py start <name>` on podman-1.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_manage.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import manage


def make_repo(root: Path):
    """Minimal repo skeleton with one podman service, one podman infra unit
    and one docker service."""
    (root / "podman/infrastructure/traefik").mkdir(parents=True)
    (root / "podman/infrastructure/traefik/traefik.container").write_text("[Container]\n")
    (root / "podman/infrastructure/traefik/traefik-public.network").write_text("[Network]\n")
    (root / "podman/infrastructure/traefik/dynamic").mkdir()
    (root / "podman/infrastructure/traefik/dynamic/legacy-docker1.yml").write_text("tcp:\n")
    (root / "podman/services/whoami").mkdir(parents=True)
    (root / "podman/services/whoami/whoami.container").write_text("[Container]\n")
    (root / "docker/services/gitea").mkdir(parents=True)
    (root / "docker/services/gitea/docker-compose.yml").write_text("services:\n")
    (root / ".env").write_text("DOCKERDIR=/mnt/appdata\nHOST_DOMAIN=example.com\n# comment\n")


class TestPodmanQuadletManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_repo(self.root)
        self.quadlet_dir = self.root / "quadlets"
        self.mgr = manage.PodmanQuadletManager(
            base_path=self.root, quadlet_dir=self.quadlet_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_infrastructure_service(self):
        self.assertEqual(self.mgr.get_service_path("traefik"),
                         self.root / "podman/infrastructure/traefik")

    def test_finds_application_service(self):
        self.assertEqual(self.mgr.get_service_path("whoami"),
                         self.root / "podman/services/whoami")

    def test_unknown_service_is_none(self):
        self.assertIsNone(self.mgr.get_service_path("gitea"))  # docker, not podman

    def test_container_units(self):
        self.assertEqual(self.mgr.container_units("traefik"), ["traefik.service"])

    def test_sync_files_copies_units_and_dynamic(self):
        self.mgr.sync_files("traefik")
        self.assertTrue((self.quadlet_dir / "traefik.container").exists())
        self.assertTrue((self.quadlet_dir / "traefik-public.network").exists())
        # dynamic/ goes to ${DOCKERDIR}/<service>/dynamic/ - here redirected
        # into the tmp tree via dockerdir override
        self.assertTrue((self.mgr.dockerdir / "traefik/dynamic/legacy-docker1.yml").exists())


class TestDispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_docker_manager_ignores_podman_tree(self):
        docker = manage.DockerComposeManager(str(self.root))
        self.assertIsNone(docker.get_service_path("whoami"))
        self.assertIsNotNone(docker.get_service_path("gitea"))

    def test_parse_env(self):
        env = manage.parse_env(self.root / ".env")
        self.assertEqual(env["DOCKERDIR"], "/mnt/appdata")
        self.assertEqual(env["HOST_DOMAIN"], "example.com")
        self.assertNotIn("# comment", env)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python3 -m unittest tests.test_manage -v
```

Expected: FAIL/ERROR — `manage` has no `PodmanQuadletManager`, no `parse_env`.

- [ ] **Step 3: Implement in manage.py**

Add after `DockerComposeManager` (style-matched to the existing class). Note: in `PodmanQuadletManager.sync_files`, `dockerdir` is overridable for tests but defaults to `DOCKERDIR` from the repo `.env`:

```python
def parse_env(env_path) -> Dict[str, str]:
    """Tiny KEY=VALUE parser for the repo .env (no quoting rules needed)."""
    env = {}
    for line in Path(env_path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


class PodmanQuadletManager:
    """Manages rootless podman quadlet services.

    Unit files live in the repo under podman/{infrastructure,services}/<name>/
    and must be synced into ~/.config/containers/systemd/ before the systemd
    user manager can see them. Everything here talks to the *user* manager -
    no root, no daemon. Run on the podman host, same reasoning as the compose
    manager: bind-mount paths only exist there.
    """

    UNIT_SUFFIXES = (".container", ".network", ".volume", ".pod")

    def __init__(self, base_path: Optional[str] = None, quadlet_dir: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent
        self.podman_dir = self.base_path / "podman"
        self.services_dir = self.podman_dir / "services"
        self.infrastructure_dir = self.podman_dir / "infrastructure"
        self.quadlet_dir = Path(quadlet_dir) if quadlet_dir else Path.home() / ".config/containers/systemd"
        env_file = self.base_path / ".env"
        env = parse_env(env_file) if env_file.exists() else {}
        self.dockerdir = Path(env.get("DOCKERDIR", "/mnt/appdata"))

    def get_service_path(self, service: str) -> Optional[Path]:
        for parent in (self.infrastructure_dir, self.services_dir):
            path = parent / service
            if path.is_dir() and any(f.suffix in self.UNIT_SUFFIXES for f in path.iterdir()):
                return path
        return None

    def unit_files(self, service: str) -> List[Path]:
        path = self.get_service_path(service)
        if not path:
            raise ValueError(f"Podman service '{service}' not found")
        return sorted(f for f in path.iterdir() if f.suffix in self.UNIT_SUFFIXES)

    def container_units(self, service: str) -> List[str]:
        """Systemd unit names quadlet generates from the .container files."""
        return [f.stem + ".service" for f in self.unit_files(service)
                if f.suffix == ".container"]

    def sync_files(self, service: str):
        """Copy unit files to the quadlet dir and dynamic/ config (if any)
        to ${DOCKERDIR}/<service>/dynamic/. No systemd interaction."""
        import shutil
        self.quadlet_dir.mkdir(parents=True, exist_ok=True)
        for f in self.unit_files(service):
            shutil.copy2(f, self.quadlet_dir / f.name)
        dynamic = self.get_service_path(service) / "dynamic"
        if dynamic.is_dir():
            target = self.dockerdir / service / "dynamic"
            target.mkdir(parents=True, exist_ok=True)
            for f in dynamic.iterdir():
                if f.is_file():
                    shutil.copy2(f, target / f.name)

    def sync(self, service: str):
        self.sync_files(service)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)

    def _systemctl(self, action: str, service: str) -> bool:
        try:
            for unit in self.container_units(service):
                Logger.info(f"systemctl --user {action} {unit}")
                subprocess.run(["systemctl", "--user", action, unit], check=True)
            return True
        except (subprocess.CalledProcessError, ValueError) as e:
            Logger.error(f"Failed to {action} {service}: {e}")
            return False

    def start_service(self, service: str) -> bool:
        self.sync(service)
        ok = self._systemctl("start", service)
        if ok:
            Logger.success(f"Started {service}")
        return ok

    def stop_service(self, service: str) -> bool:
        ok = self._systemctl("stop", service)
        if ok:
            Logger.success(f"Stopped {service}")
        return ok

    def restart_service(self, service: str) -> bool:
        self.sync(service)
        return self._systemctl("restart", service)

    def update_service(self, service: str) -> bool:
        """Quadlets update via podman auto-update (AutoUpdate=registry)."""
        self.sync(service)
        try:
            subprocess.run(["podman", "auto-update"], check=True)
            Logger.success(f"auto-update run (covers {service} and all AutoUpdate units)")
            return True
        except subprocess.CalledProcessError as e:
            Logger.error(f"auto-update failed: {e}")
            return False

    def show_logs(self, service: str, follow: bool = True, tail: int = 100):
        for unit in self.container_units(service):
            cmd = ["journalctl", "--user", "-u", unit, "-n", str(tail)]
            if follow:
                cmd.append("-f")
            try:
                subprocess.run(cmd)
            except KeyboardInterrupt:
                Logger.info("Log streaming stopped")

    def show_status(self, service: str) -> bool:
        ok = True
        for unit in self.container_units(service):
            result = subprocess.run(["systemctl", "--user", "status", unit, "--no-pager"])
            ok = ok and result.returncode == 0
        return ok

    def is_service_running(self, service: str) -> bool:
        try:
            return all(
                subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit]).returncode == 0
                for unit in self.container_units(service))
        except ValueError:
            return False
```

Then wire dispatch into `main()`:

1. After `manager = DockerComposeManager(args.path)` add `podman_manager = PodmanQuadletManager(args.path)`.
2. Add a helper just above the action loop:

```python
    def pick(service):
        return podman_manager if podman_manager.get_service_path(service) else manager
```

3. In the action loop, replace each `manager.` call with `pick(service).` (start/stop/restart/update/logs/status/is_service_running), and change the existence check to `if not manager.get_service_path(service) and not podman_manager.get_service_path(service):`.
4. In the `--all` branch, extend the service list: `args.services = all_services["infrastructure"] + all_services["applications"] + sorted(set(p.name for parent in (podman_manager.infrastructure_dir, podman_manager.services_dir) if parent.exists() for p in parent.iterdir() if podman_manager.get_service_path(p.name)))`.
5. Guard `check_dependencies()`: docker's check must not block podman-only hosts. Change the call site to only hard-fail when a requested service resolves to the docker manager (simplest: move the `check_dependencies` call into the action loop, first time `pick(service)` returns the docker manager).

- [ ] **Step 4: Run tests, verify they pass**

```bash
python3 -m unittest tests.test_manage -v
```

Expected: all PASS.

- [ ] **Step 5: Sanity-check docker dispatch still works (on docker-1, read-only)**

```bash
ssh ubuntu@192.168.1.100 'cd /mnt/appdata/homelab && git stash list >/dev/null; python3 manage.py list' 
```

Expected: unchanged service list, all green — proves the docker path didn't regress. (Do NOT pull the new manage.py onto docker-1 yet; this runs the old one as a baseline. The new one reaches docker-1 whenever the repo is next pulled there — its behavior for docker services is unchanged.)

- [ ] **Step 6: Commit**

```bash
git add manage.py tests/test_manage.py
git commit -m "Teach manage.py to drive podman quadlet services"
git push
```

---

### Task 3: Quadlet scaffolding on the VM — network + whoami pilot

**Files:**
- Create: `podman/infrastructure/traefik/traefik-public.network`
- Create: `podman/services/whoami/whoami.container`

**Interfaces:**
- Consumes: `PodmanQuadletManager` from Task 2; the VM from Task 1.
- Produces: the `traefik-public` podman network; a running `whoami` container joined to it with traefik labels; the repo cloned at `/mnt/appdata/homelab` on podman-1 with `.env`; **a verified answer to whether systemd `${VAR}` expansion works in quadlet-generated ExecStart** (Task 4+ rely on the same mechanism).

- [ ] **Step 1: Write `podman/infrastructure/traefik/traefik-public.network`**

```ini
[Unit]
Description=Shared ingress network (traefik + routed services)

[Network]
# Netavark allocates from 10.88.0.0/16 - invariant: podman networks must
# never land in 192.168.x (collides with LAN/VPN and blackholes traffic).
NetworkName=traefik-public
```

- [ ] **Step 2: Write `podman/services/whoami/whoami.container`**

```ini
[Unit]
Description=whoami - pilot proving quadlets, labels and the ingress chain
RequiresMountsFor=/mnt/main /mnt/appdata

[Container]
Image=docker.io/traefik/whoami:latest
ContainerName=whoami
Network=traefik-public.network
AutoUpdate=registry
Label=traefik.enable=true
Label=traefik.docker.network=traefik-public
Label=traefik.http.routers.whoami.entrypoints=websecure
Label=traefik.http.routers.whoami.rule=Host(`whoami.${HOST_DOMAIN}`)
Label=traefik.http.routers.whoami.tls.certresolver=cloudflare
Label=traefik.http.services.whoami.loadbalancer.server.port=80

[Service]
# For ${HOST_DOMAIN} expansion in the Label lines: quadlet turns [Container]
# keys into podman-run arguments on ExecStart, where systemd substitutes
# ${VAR} from this file. Secrets never enter the container env this way.
EnvironmentFile=/mnt/appdata/homelab/.env
Restart=always

[Install]
WantedBy=default.target
```

- [ ] **Step 3: Commit and push**

```bash
git add podman/
git commit -m "Add traefik-public network and whoami pilot quadlets"
git push
```

- [ ] **Step 4: Clone the repo onto podman-1 and copy .env**

```bash
ssh ubuntu@192.168.1.110 'git clone --recurse-submodules https://github.com/jondef/homelab.git /mnt/appdata/homelab'
scp ubuntu@192.168.1.100:/mnt/appdata/homelab/.env /tmp/homelab.env
scp /tmp/homelab.env ubuntu@192.168.1.110:/mnt/appdata/homelab/.env
rm /tmp/homelab.env
```

(Adjust the docker-1 repo path if it lives elsewhere; `manage.py`'s epilog says `/mnt/appdata`.)

- [ ] **Step 5: Deploy network + whoami via manage.py**

```bash
ssh ubuntu@192.168.1.110 'cd /mnt/appdata/homelab &&
  python3 manage.py start traefik &&   # only the .network unit exists yet - sync is what matters
  python3 manage.py start whoami'
```

Note: `start traefik` at this point syncs `traefik-public.network` (no `.container` there yet, so `container_units` is empty and nothing starts — that's fine).

- [ ] **Step 6: Verify unit and label expansion (decision point)**

```bash
ssh ubuntu@192.168.1.110 '
  systemctl --user is-active whoami.service &&
  podman network inspect traefik-public --format "{{range .Subnets}}{{.Subnet}}{{end}}" &&
  podman inspect whoami --format "{{index .Config.Labels \"traefik.http.routers.whoami.rule\"}}"'
```

Expected: `active`; a `10.88.x.x/xx` subnet (NOT 192.168.x); rule shows ``Host(`whoami.mercantus.ch`)`` with the **real domain expanded**.

**If the rule shows literal `${HOST_DOMAIN}`:** quadlet escaped the expansion. Fallback: replace `${HOST_DOMAIN}` with the literal domain in every `Label=` line of this plan's unit files (the domain is public in the repo docs already; secrets like the cloudflare token in Task 4 must then be injected via `[Container] EnvironmentFile=` pointing at a VM-local env file instead — never hardcoded). Re-deploy and re-verify before continuing.

- [ ] **Step 7: Commit any fallback edits (else nothing to commit)**

```bash
git status --short  # if fallback edits were needed:
git add podman/ && git commit -m "Hardcode domain in quadlet labels (no env expansion)" && git push
```

---

### Task 4: Traefik quadlet with staging certs + legacy passthrough

**Files:**
- Create: `podman/infrastructure/traefik/traefik.container`
- Create: `podman/infrastructure/traefik/dynamic/legacy-docker1.yml`

**Interfaces:**
- Consumes: `traefik-public.network` (Task 3), podman user socket (Task 1), `.env` on podman-1 (`HOST_DOMAIN`, `CLOUDFLARE_DNS_EMAIL`, `CLOUDFLARE_DNS_API_TOKEN`).
- Produces: traefik serving 80/443 on 192.168.1.110 with a staging wildcard cert; label-discovered routing (whoami); TLS passthrough to docker-1 for every un-migrated hostname. Task 5 flips this same unit to production ACME.

- [ ] **Step 1: Write `podman/infrastructure/traefik/traefik.container`**

Config carried over from `docker/infrastructure/traefik/docker-compose.yml` — same flags, three changes: the socket volume points at the podman user socket (`%t` = `/run/user/1000`), the staging caserver is ON (removed in Task 5), and watchtower's label became `AutoUpdate=registry`.

```ini
[Unit]
Description=Traefik ingress (rootless)
RequiresMountsFor=/mnt/main /mnt/appdata

[Container]
Image=docker.io/library/traefik:3.7
ContainerName=traefik
Network=traefik-public.network
PublishPort=80:80
PublishPort=443:443
Volume=/etc/localtime:/etc/localtime:ro
Volume=/usr/share/zoneinfo:/usr/share/zoneinfo:ro
Volume=%t/podman/podman.sock:/var/run/docker.sock:ro
Volume=${DOCKERDIR}/traefik/logs:/var/log/traefik
Volume=${DOCKERDIR}/traefik:/traefik
Environment=CLOUDFLARE_DNS_API_TOKEN=${CLOUDFLARE_DNS_API_TOKEN}
AutoUpdate=registry
Label=traefik.enable=true
Label=traefik.docker.network=traefik-public
Label=traefik.http.routers.traefik.entrypoints=websecure
Label=traefik.http.routers.traefik.tls.certresolver=cloudflare
Label=traefik.http.routers.traefik.rule=Host(`traefik.${HOST_DOMAIN}`)
Label=traefik.http.routers.traefik.service=api@internal
Label=traefik.http.routers.traefik.middlewares=authelia@docker
Exec=--log.level=ERROR \
  --log.filePath=/var/log/traefik/traefik.log \
  --accessLog=true \
  --accessLog.format=json \
  --accessLog.fields.headers.names.X-Request-Id=keep \
  --accessLog.filePath=/var/log/traefik/access.log \
  --api.insecure=false \
  --api.dashboard=true \
  --global.sendAnonymousUsage=false \
  --global.checkNewVersion=false \
  --providers.docker=true \
  --providers.docker.exposedbydefault=false \
  --providers.docker.network=traefik-public \
  --providers.file.directory=/traefik/dynamic \
  --providers.file.watch=true \
  --entrypoints.web.forwardedHeaders.trustedIPs=173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,104.24.0.0/14,172.64.0.0/13,131.0.72.0/22,2400:cb00::/32,2606:4700::/32,2803:f800::/32,2405:b500::/32,2405:8100::/32,2a06:98c0::/29,2c0f:f248::/32 \
  --entrypoints.websecure.forwardedHeaders.trustedIPs=173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,104.24.0.0/14,172.64.0.0/13,131.0.72.0/22,2400:cb00::/32,2606:4700::/32,2803:f800::/32,2405:b500::/32,2405:8100::/32,2a06:98c0::/29,2c0f:f248::/32 \
  --entrypoints.web.address=:80 \
  --entrypoints.web.http.redirections.entryPoint.to=websecure \
  --entrypoints.web.http.redirections.entryPoint.scheme=https \
  --entrypoints.web.http.redirections.entryPoint.permanent=true \
  --entrypoints.websecure.address=:443 \
  --entrypoints.websecure.http.tls=true \
  --entrypoints.websecure.http.tls.certResolver=cloudflare \
  --entrypoints.websecure.http.tls.domains[0].main=${HOST_DOMAIN} \
  --entrypoints.websecure.http.tls.domains[0].sans=*.${HOST_DOMAIN} \
  --entryPoints.websecure.transport.respondingTimeouts.readTimeout=12h \
  --entryPoints.websecure.transport.respondingTimeouts.writeTimeout=12h \
  --entryPoints.websecure.transport.respondingTimeouts.idleTimeout=3m \
  --certificatesresolvers.cloudflare.acme.dnschallenge=true \
  --certificatesresolvers.cloudflare.acme.dnschallenge.provider=cloudflare \
  --certificatesresolvers.cloudflare.acme.dnschallenge.delaybeforecheck=0 \
  --certificatesresolvers.cloudflare.acme.email=${CLOUDFLARE_DNS_EMAIL} \
  --certificatesresolvers.cloudflare.acme.storage=/traefik/acme.json \
  --certificatesresolvers.cloudflare.acme.caserver=https://acme-staging-v02.api.letsencrypt.org/directory

[Service]
EnvironmentFile=/mnt/appdata/homelab/.env
Restart=always

[Install]
WantedBy=default.target
```

Note the dashboard router references `authelia@docker`, which doesn't exist until Task 6 — traefik disables just that router and logs an error; every other router works. Expected until Task 6.

- [ ] **Step 2: Write `podman/infrastructure/traefik/dynamic/legacy-docker1.yml`**

One TCP passthrough router per hostname still living on docker-1 (enumerated from the active compose labels; excludes `auth`, `traefik` and `whoami`, which live on podman-1). TLS for these is still terminated by docker-1's traefik with its existing production cert. **Migrating a service later = delete its router here, add its quadlet.**

```yaml
# Hostnames still served by docker-1 (192.168.1.100). SNI-routed TLS
# passthrough: the connection is handed over un-terminated, docker-1's
# traefik still does TLS with its own certificate.
tcp:
  routers:
    legacy-apex:
      entryPoints: [websecure]
      rule: HostSNI(`mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-jon:
      entryPoints: [websecure]
      rule: HostSNI(`jon.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-cloud:
      entryPoints: [websecure]
      rule: HostSNI(`cloud.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-nocodb:
      entryPoints: [websecure]
      rule: HostSNI(`nocodb.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-collabora:
      entryPoints: [websecure]
      rule: HostSNI(`collabora.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-cyberchef:
      entryPoints: [websecure]
      rule: HostSNI(`cyberchef.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-garage:
      entryPoints: [websecure]
      rule: HostSNI(`garage.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-s3:
      entryPoints: [websecure]
      rule: HostSNI(`s3.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-web:
      entryPoints: [websecure]
      rule: HostSNI(`web.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-git:
      entryPoints: [websecure]
      rule: HostSNI(`git.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-vdi:
      entryPoints: [websecure]
      rule: HostSNI(`vdi.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-photos:
      entryPoints: [websecure]
      rule: HostSNI(`photos.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-tools:
      entryPoints: [websecure]
      rule: HostSNI(`tools.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-stream:
      entryPoints: [websecure]
      rule: HostSNI(`stream.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-books:
      entryPoints: [websecure]
      rule: HostSNI(`books.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-bookmarks:
      entryPoints: [websecure]
      rule: HostSNI(`bookmarks.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-n8n:
      entryPoints: [websecure]
      rule: HostSNI(`n8n.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-docs:
      entryPoints: [websecure]
      rule: HostSNI(`docs.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-design:
      entryPoints: [websecure]
      rule: HostSNI(`design.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-latex:
      entryPoints: [websecure]
      rule: HostSNI(`latex.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-pdf:
      entryPoints: [websecure]
      rule: HostSNI(`pdf.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-uptime:
      entryPoints: [websecure]
      rule: HostSNI(`uptime.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
    legacy-vault:
      entryPoints: [websecure]
      rule: HostSNI(`vault.mercantus.ch`)
      tls: {passthrough: true}
      service: docker1
  services:
    docker1:
      loadBalancer:
        servers:
          - address: "192.168.1.100:443"
```

Before committing, cross-check the list against `grep -rh "rule=Host" docker/infrastructure docker/services --include=docker-compose.yml` — services may have changed since this plan was written.

- [ ] **Step 3: Commit and push**

```bash
git add podman/infrastructure/traefik/
git commit -m "Add traefik quadlet (staging ACME) and legacy passthrough list"
git push
```

- [ ] **Step 4: Prepare state dirs and deploy on podman-1**

```bash
ssh ubuntu@192.168.1.110 '
  mkdir -p /mnt/appdata/traefik/logs /mnt/appdata/traefik/dynamic &&
  cd /mnt/appdata/homelab && git pull &&
  python3 manage.py start traefik &&
  systemctl --user status traefik --no-pager'
```

Expected: `active (running)`. Check startup errors: `journalctl --user -u traefik -n 50` — the only acceptable error is the missing `authelia@docker` middleware (dashboard router, fixed in Task 6).

- [ ] **Step 5: Verify staging cert + whoami routing**

From this machine (LAN):

```bash
echo | openssl s_client -connect 192.168.1.110:443 -servername whoami.mercantus.ch 2>/dev/null | openssl x509 -noout -issuer
curl -sk --resolve whoami.mercantus.ch:443:192.168.1.110 https://whoami.mercantus.ch
```

Expected: issuer contains `(STAGING)`; whoami responds with its hostname/headers dump.

- [ ] **Step 6: Verify real client IP (decision point — the pasta test)**

From this machine (its LAN IP visible via `ipconfig getifaddr en0`):

```bash
curl -sk --resolve whoami.mercantus.ch:443:192.168.1.110 https://whoami.mercantus.ch | grep -E "X-Forwarded-For|X-Real-Ip"
```

Expected: **this machine's LAN IP** (e.g. `192.168.0.x`/`192.168.1.x`).

**If it shows `10.88.x.x`, `127.0.0.1` or the pasta gateway instead:** rootless port publishing on a bridge network is eating the source address. Switch traefik to **systemd socket activation** (traefik ≥ 3.2 supports it; sockets are accepted by the user manager in the host namespace, so the real peer address survives):

1. Create `~/.config/systemd/user/web.socket` and `websecure.socket` on podman-1 (these are plain user units, not quadlets — add them to the repo under `podman/infrastructure/traefik/` and extend `manage.py`'s `UNIT_SUFFIXES`+sync convention for `.socket` files):

```ini
# web.socket
[Socket]
ListenStream=0.0.0.0:80
BindIPv6Only=both
FileDescriptorName=web
Service=traefik.service

[Install]
WantedBy=sockets.target
```

```ini
# websecure.socket
[Socket]
ListenStream=0.0.0.0:443
BindIPv6Only=both
FileDescriptorName=websecure
Service=traefik.service

[Install]
WantedBy=sockets.target
```

2. In `traefik.container`: delete both `PublishPort=` lines, delete `[Install]` (the sockets own activation now).
3. `systemctl --user daemon-reload && systemctl --user enable --now web.socket websecure.socket && systemctl --user restart traefik`.
4. Traefik matches sockets to entrypoints by `FileDescriptorName` (= entrypoint names `web`/`websecure`). Re-run the client-IP check; commit the changes.

- [ ] **Step 7: Verify legacy passthrough**

```bash
curl -sI --resolve cloud.mercantus.ch:443:192.168.1.110 https://cloud.mercantus.ch | head -3
curl -sI --resolve vault.mercantus.ch:443:192.168.1.110 https://vault.mercantus.ch | head -3
curl -sI --resolve git.mercantus.ch:443:192.168.1.110 https://git.mercantus.ch | head -3
```

Expected: real responses from nextcloud/vaultwarden/gitea **with valid production certificates** (no `-k` needed — TLS is docker-1's traefik, passed through). If you get the staging cert instead, the SNI router didn't match — check `journalctl --user -u traefik` and the dynamic file landed in `/mnt/appdata/traefik/dynamic/`.

---

### Task 5: Flip ACME to production

**Files:**
- Modify: `podman/infrastructure/traefik/traefik.container` (one deleted line)

**Interfaces:**
- Consumes: working staging setup from Task 4.
- Produces: production wildcard cert on podman-1's traefik (success criterion 1).

- [ ] **Step 1: Remove the staging caserver line**

In `traefik.container`, delete the line:

```
  --certificatesresolvers.cloudflare.acme.caserver=https://acme-staging-v02.api.letsencrypt.org/directory
```

(and the trailing ` \` on the now-last `--certificatesresolvers.cloudflare.acme.storage=/traefik/acme.json` line).

- [ ] **Step 2: Commit and push**

```bash
git add podman/infrastructure/traefik/traefik.container
git commit -m "Traefik on podman-1: production ACME"
git push
```

- [ ] **Step 3: Clear staging cert state and redeploy**

```bash
ssh ubuntu@192.168.1.110 '
  cd /mnt/appdata/homelab && git pull &&
  python3 manage.py stop traefik &&
  rm -f /mnt/appdata/traefik/acme.json &&
  python3 manage.py start traefik'
```

- [ ] **Step 4: Verify production wildcard**

```bash
sleep 30 && echo | openssl s_client -connect 192.168.1.110:443 -servername whoami.mercantus.ch 2>/dev/null | openssl x509 -noout -issuer -ext subjectAltName
```

Expected: issuer `Let's Encrypt` (no STAGING); SAN contains `mercantus.ch` and `*.mercantus.ch`. DNS-01 needs no inbound port, so this works pre-flip.

---

### Task 6: Migrate authelia

**Files:**
- Create: `podman/infrastructure/authelia/authelia.container`
- Delete: `docker/infrastructure/authelia/` (the move that marks "runs on podman now")

**Interfaces:**
- Consumes: running traefik from Task 5; authelia state at `docker-1:/mnt/appdata/authelia/`.
- Produces: authelia on podman-1 publishing the `authelia@docker` forward-auth middleware; the traefik dashboard router starts working (success criterion 4 pre-flip).

- [ ] **Step 1: Write `podman/infrastructure/authelia/authelia.container`**

Carried over from `docker/infrastructure/authelia/docker-compose.yml`. Deliberate change: the compose file's `user: "1000:1000"` is **dropped** — under rootless podman, container-root already maps to host uid 1000 (ubuntu), while a container uid 1000 would map to an unrelated subuid and break file ownership on the volume. Watchtower's label became `AutoUpdate=registry`.

```ini
[Unit]
Description=Authelia forward-auth (SSO for traefik routers)
RequiresMountsFor=/mnt/main /mnt/appdata

[Container]
Image=docker.io/authelia/authelia:4
ContainerName=authelia
Network=traefik-public.network
Volume=${DOCKERDIR}/authelia/config:/config
Environment=TZ=${TZ}
AutoUpdate=registry
Label=traefik.enable=true
Label=traefik.docker.network=traefik-public
Label=traefik.http.routers.authelia.entrypoints=websecure
Label=traefik.http.routers.authelia.tls.certresolver=cloudflare
Label=traefik.http.routers.authelia.rule=Host(`auth.${HOST_DOMAIN}`)
Label=traefik.http.middlewares.authelia.forwardauth.address=http://authelia:9091/api/verify?rd=https://auth.${HOST_DOMAIN}
Label=traefik.http.middlewares.authelia.forwardauth.trustForwardHeader=true
Label=traefik.http.middlewares.authelia.forwardauth.authResponseHeaders=Remote-User,Remote-Groups,Remote-Name,Remote-Email

[Service]
EnvironmentFile=/mnt/appdata/homelab/.env
Restart=always

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Move the service in the repo (docker/ → podman/), commit, push**

```bash
git rm -r docker/infrastructure/authelia
git add podman/infrastructure/authelia/authelia.container
git commit -m "Migrate authelia to a quadlet on podman-1"
git push
```

- [ ] **Step 3: Stop authelia on docker-1 and copy its state**

```bash
# Run compose from the service directory - the project name derives from the
# cwd, matching how manage.py started it. -f from the repo root would target
# a different (nonexistent) project.
ssh ubuntu@192.168.1.100 'cd /mnt/appdata/homelab/docker/infrastructure/authelia && docker compose --env-file /mnt/appdata/homelab/.env down'
# -A: agent forwarding - podman-1 has no key authorized on docker-1.
ssh -A ubuntu@192.168.1.110 'rsync -a ubuntu@192.168.1.100:/mnt/appdata/authelia/ /mnt/appdata/authelia/'
```

(Do NOT `git pull` on docker-1 before this stop — after the pull the compose dir is gone from its checkout. The stop must happen while the directory still exists, or fall back to `docker stop authelia && docker rm authelia`.)

- [ ] **Step 4: Start the quadlet and verify**

```bash
ssh ubuntu@192.168.1.110 'cd /mnt/appdata/homelab && git pull && python3 manage.py start authelia'
curl -sI --resolve auth.mercantus.ch:443:192.168.1.110 https://auth.mercantus.ch | head -3
curl -sI --resolve traefik.mercantus.ch:443:192.168.1.110 https://traefik.mercantus.ch | head -3
```

Expected: `auth.` returns authelia (200/302 to its login UI); `traefik.` returns a **302 redirect to auth.mercantus.ch** — proving the forward-auth middleware resolved and the dashboard router came alive. Then log in at `https://auth.mercantus.ch` (via `--resolve` in a browser is awkward — a temporary `/etc/hosts` entry `192.168.1.110 auth.mercantus.ch traefik.mercantus.ch` works) and confirm credentials + TOTP still work against the rsync'd state. Remove the hosts entry afterwards.

**Rollback if broken:** `python3 manage.py stop authelia` on podman-1; on docker-1: `git revert` the move commit (or `git stash`-restore the compose dir) and `docker compose ... up -d`; state rsyncs back the same way.

---

### Task 7: Flip the front door (OPNsense) + soak + rollback rehearsal

**Files:** none (router config + Cloudflare DNS; no repo changes)

**Interfaces:**
- Consumes: fully verified podman-1 ingress (Tasks 4–6).
- Produces: all public traffic enters via podman-1 (success criteria 2, 3, 7).

- [ ] **Step 1: Ensure `whoami` DNS exists at Cloudflare**

In the Cloudflare dashboard for the domain: if there is no wildcard `*` record, add `whoami` as a **proxied** CNAME/A matching how the other subdomains are set up. (Manual; skip if a wildcard record covers it.)

- [ ] **Step 2: Flip the port forward (manual, OPNsense UI)**

Firewall → NAT → Port Forward: the rules forwarding **80 and 443 (TCP and UDP)** currently target `192.168.1.100`. Change the redirect target on each to `192.168.1.110`. Apply. Check any associated firewall rules updated with them (the cloudflare-sources-only filter must keep applying — it filters by *source*, so it is independent of the new target, but eyeball it).

- [ ] **Step 3: Verify from outside the LAN**

From a phone on cellular (or any off-LAN host):

- `https://whoami.mercantus.ch` — loads with a valid cert; the response's `X-Forwarded-For` contains the phone's **public IP** (real client IP surviving cloudflare → pasta/socket → traefik). Not a 10.88.x, not a cloudflare edge IP.
- `https://cloud.mercantus.ch`, `https://photos.mercantus.ch`, `https://git.mercantus.ch`, `https://stream.mercantus.ch` — all load normally (passthrough).
- `https://auth.mercantus.ch` — login works end-to-end including TOTP.
- `https://traefik.mercantus.ch` — redirects to auth, then shows the dashboard after login (forward-auth through the new chain).
- `https://uptime.mercantus.ch` — uptime-kuma's own dashboard: all monitors green.

- [ ] **Step 4: Rollback rehearsal (success criterion 7)**

1. OPNsense: flip the 80/443 targets back to `192.168.1.100`. Apply.
2. From cellular: `cloud.` and `vault.` load fine the old way (authelia-protected routes on docker-1 would fail — authelia moved; that's expected and exactly what a real rollback would need the reverse-rsync for).
3. Flip forward to `192.168.1.110` again. Apply.
4. Re-run the Step 3 spot checks.

- [ ] **Step 5: Soak**

Leave it for at least a day. uptime-kuma alerts on anything broken through the new chain. Check `journalctl --user -u traefik` on podman-1 and `/mnt/appdata/traefik/logs/access.log` for real client IPs in entries.

---

### Task 8: Reboot test, auto-update check, documentation

**Files:**
- Modify: `.resources/infrastructure.md`

**Interfaces:**
- Consumes: everything prior.
- Produces: success criteria 5 and 6 verified; docs reflect reality.

- [ ] **Step 1: Unattended reboot test (success criterion 6)**

```bash
ssh ubuntu@192.168.1.110 'sudo reboot'
sleep 120
ssh ubuntu@192.168.1.110 '
  systemctl --user is-active traefik authelia whoami &&
  journalctl --user -u traefik -b --no-pager | head -5'
curl -sI https://whoami.mercantus.ch | head -1
```

Expected: all three `active`, journal shows they started at boot (linger) — and the public check works without anyone having logged in. If a unit failed with a mount-related error, `RequiresMountsFor` did its job by refusing to start before storage — investigate the mount, not the unit.

- [ ] **Step 2: Auto-update check (success criterion 5)**

```bash
ssh ubuntu@192.168.1.110 '
  systemctl --user enable --now podman-auto-update.timer &&
  systemctl --user list-timers podman-auto-update.timer --no-pager &&
  podman auto-update --dry-run'
```

Expected: timer scheduled; dry-run lists traefik, authelia and whoami with `registry` policy (pending/false status is fine — it checked, that's the mechanism proven).

- [ ] **Step 3: Update `.resources/infrastructure.md`**

Concrete edits:

1. **Topology diagram** — under `vmbr1`, add above docker-1 and move the `◄──` marker:

```
  ├─ podman-1 VM 210       192.168.1.110    ◄── 80, 443 passed on by OPNsense
  │                                             traefik + authelia (rootless podman)
  ├─ docker-1 VM 201       192.168.1.100    legacy services behind TLS passthrough
```

2. **"What the upstream router forwards"** — change `docker-1 :80/:443` to `podman-1 :80/:443`.

3. **Ingress section** — replace the chain line `:443 → home router → OPNsense → docker-1` with `:443 → home router → OPNsense → podman-1`, and add after the chain diagram:

```
- **Two traefiks during the podman migration.** podman-1's rootless traefik is
  the front door. Hostnames not yet migrated are SNI-matched in
  `podman/infrastructure/traefik/dynamic/legacy-docker1.yml` and passed
  through, TLS un-terminated, to docker-1's traefik (192.168.1.100:443),
  which still holds its own certificate. Migrating a service = delete its
  passthrough line + add its quadlet.
```

4. **Container networking** — add:

```
Podman (netavark) allocates from 10.88.0.0/16 on podman-1. Same rule as
docker's 172.x pool: never let it allocate in 192.168.x.
```

5. **Invariants** — extend #4: `Anything mounting docker.sock is coupled to the Docker version` → add `; on podman-1 the same applies to the podman user socket and podman version bumps.` And add:

```
6. **Rootless quadlets declare their mounts.** Every `.container` unit carries
   `RequiresMountsFor=/mnt/main /mnt/appdata` - the per-unit version of
   docker-1's daemon drop-in, same shadow-data lesson.
```

- [ ] **Step 4: Commit**

```bash
git add .resources/infrastructure.md
git commit -m "Document podman-1 as the front door"
git push
```

---

## Self-Review Notes

- **Spec coverage:** VM/terraform → Task 1; repo layout + conventions + manage.py → Tasks 2–3; ingress (socket discovery, fresh ACME staging→prod, passthrough, client IP) → Tasks 4–5; authelia → Task 6; cutover + rollback → Task 7; ops (logrotate in cloud-init Task 1, auto-update Task 8, journald implicit) and success criteria 1–7 → Tasks 4 (crit 2 LAN-level), 5 (crit 1), 4 (crit 3), 6 (crit 4), 8 (crit 5, 6), 7 (crit 2 public, 3, 7). QUIC note is informational, no task needed.
- **Two deliberate deviations from the spec, both argued inline:** labels use `${HOST_DOMAIN}` expansion via `[Service] EnvironmentFile` (with a tested fallback to hardcoding, Task 3 step 6), and `legacy-docker1.yml` hardcodes the domain (public in the docs already).
- **Known uncertainty, handled as decision points, not assumptions:** systemd `${VAR}` expansion through quadlet ExecStart (Task 3 step 6) and rootless source-IP preservation with published ports on a bridge network (Task 4 step 6, with a complete socket-activation fallback).
