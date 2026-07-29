# Podman Migration — Foundation Phase Design

**Date:** 2026-07-29
**Status:** Approved

## Goal

Begin migrating the homelab from Docker Compose on docker-1 to rootless Podman
with quadlets, motivated by dropping the Docker daemon and gaining rootless
security. This phase builds the foundation and takes the riskiest step first:
a new podman VM becomes the front door for all web traffic ("early flip"),
serving traefik, authelia and a whoami pilot natively, while every un-migrated
service is reached through TLS passthrough back to docker-1.

Later phases (separate specs): migrate the remaining ~23 stacks in batches,
then decommission docker-1.

## Out of scope for this phase

- Migrating any service other than traefik, authelia and whoami
- Decommissioning docker-1 or moving its terraform-owned resources (one
  exception is prepared, see the virtiofs mapping note)
- Watchtower removal — it keeps managing docker-1 until decommission
- Per-service rootless users — everything runs under one user (`ubuntu`);
  revisit only if a concrete need appears

## The VM — `terraform/podman-vm/`

A sibling of `terraform/docker-vm/`, same bpg/proxmox provider and
cloud-config pattern.

| Setting | Value | Why |
|---|---|---|
| Image | Ubuntu 26.04 LTS cloud image (resolute) | LTS **and** podman 5.7 in stock repos — no PPA. 5.x is required for pasta source-IP preservation and mature quadlets |
| VM id | 210 | docker-1 is 201, kubernetes-vm is separate |
| IP | 192.168.1.110/24, gw 192.168.1.1, vmbr1 | **Must stay ≤ .127** — tailscale advertises /25 routes, anything above is invisible remotely |
| CPU / RAM | 8 cores host-type / 16 GB dedicated, ballooning off | Starts modest; rebalance from docker-1 (32 GB) as services migrate. Ballooning off for the same database reasons as docker-1 |
| OS disk | 100 GB zvol, local-zfs, virtio0 | |
| Appdata disk | 100 GB zvol, local-zfs, virtio1, ext4 label `appdata`, mounted `/mnt/appdata` | Same mount point as docker-1 so `${DOCKERDIR}` and unit paths are identical on both VMs. Own zvol — ext4 cannot be shared between VMs |
| Bulk storage | virtiofs mapping `main` → `/mnt/main` | Same mapping as docker-1; virtiofs shares safely into multiple VMs |

**virtiofs mapping ownership:** podman-vm attaches the mapping by its name
string (`"main"`); the `proxmox_hardware_mapping_dir` **resource** stays in
docker-vm's state. ⚠️ The decommission phase must `terraform state mv` that
resource into podman-vm (or a shared module) **before** any
`terraform destroy` of docker-vm, or the mapping is destroyed under podman-vm.

**cloud-init** (differences from docker-vm's):

- Packages: `podman`, `passt`, `qemu-guest-agent` — no docker repo, no docker
- `loginctl enable-linger ubuntu` — user services start at boot without login
- `net.ipv4.ip_unprivileged_port_start=80` via sysctl.d — rootless traefik
  binds 80/443 directly
- Same fstab entries for `/mnt/appdata` (ext4 zvol) and `/mnt/main` (virtiofs)
- Enable the podman user socket: `systemctl --user enable podman.socket`
  (via a runcmd as the ubuntu user) — traefik's discovery endpoint
- No `docker.service.d/require-mounts.conf` — the mount lesson moves into
  every quadlet unit instead (below)

## Repo layout and quadlet conventions

```
podman/
  infrastructure/
    traefik/
      traefik.container
      traefik-public.network
      dynamic/
        legacy-docker1.yml      # TLS-passthrough list, one entry per un-migrated hostname
    authelia/
      authelia.container
  services/
    whoami/
      whoami.container
```

A service *moves* from `docker/` to `podman/` when it cuts over — at any
moment the repo shows exactly what runs where.

Conventions for every `.container` unit:

- `[Unit] RequiresMountsFor=/mnt/main /mnt/appdata` — the shadow-data lesson
  (bitten twice on docker-1), now declared per-unit. Works in the rootless
  user manager.
- `[Container] EnvironmentFile=` pointing at the repo `.env` — same variables
  (`DOCKERDIR`, `DATADIR`, `HOST_DOMAIN`, …) as the compose files use today.
- `[Container] AutoUpdate=registry` (equivalently the
  `io.containers.autoupdate=registry` label) — `podman-auto-update.timer`
  replaces watchtower on this VM.
- Traefik routing labels carry over verbatim from the compose files —
  including `authelia@docker` middleware references, because the docker
  provider reading the podman socket still names itself `docker`.
- `[Install] WantedBy=default.target` so linger starts them at boot.

**Deployment:** quadlets must live in `~/.config/containers/systemd/`.
`manage.py` gains a podman dispatch path: for services under `podman/` it
syncs the unit files there, runs `systemctl --user daemon-reload`, and maps
start/stop/restart/logs/status onto `systemctl --user` / `journalctl --user`.
Update = `podman auto-update`. Boot on podman-vm needs no manage.py — linger
plus systemd handle it (no `start_containers.service` on this VM).

**Networks:** `traefik-public` becomes a `.network` quadlet; per-stack private
networks follow the same pattern in later phases. Netavark allocates from
`10.88.0.0/16` — new invariant, same spirit as docker's `172.x` rule: podman
networks must never land in `192.168.x`.

## Ingress

Traefik's configuration carries over nearly verbatim (same static CLI flags,
cloudflare trusted-IP list, timeouts, wildcard DNS-01 resolver), with these
changes:

- **Discovery endpoint** is the rootless podman user socket
  (`/run/user/1000/podman/podman.sock`), mounted read-only. It speaks the
  Docker API. Invariant 4 (socket API/version coupling) applies to podman
  bumps exactly as it did to docker bumps.
- **Fresh `acme.json`** under podman-vm's `/mnt/appdata/traefik/`. Issue
  against Let's Encrypt **staging first**, flip to production only when the
  chain is verified. docker-1's traefik and its cert state are untouched.
- **Client IP:** pasta (podman 5 default) preserves the source address on
  inbound forwarded connections, so the cloudflare `trustedIPs` forwarding
  works as before. Verifying this is an explicit success criterion, not an
  assumption.
- **Legacy passthrough:** `dynamic/legacy-docker1.yml` holds one **TCP router
  per un-migrated public hostname** — a `HostSNI` rule for
  `<name>.${HOST_DOMAIN}` with `passthrough: true`, service pointing at
  `192.168.1.100:443`. TLS for those hosts is still
  terminated by docker-1's traefik with its existing certificate. Migrating a
  service later = delete its passthrough line, add its quadlet. The hostname
  list is enumerated from the current compose labels
  (`grep -r "traefik.http.routers" docker/`).
- Port 80 terminates at the new traefik and redirects to https globally, as
  today; no passthrough needed on 80.

**Known temporary regression:** QUIC (UDP 443) cannot be passthrough-routed
per-SNI. The current traefik does not enable HTTP/3, so clients already use
TCP — no observable change, but note it so nobody enables HTTP/3 on docker-1
mid-migration and wonders.

## Authelia migration

Moves in this phase because the new front door needs its forward-auth
middleware. Sequence: stop authelia on docker-1 → rsync its
`/mnt/appdata/authelia/` subtree to podman-vm → start the quadlet → verify a
protected route. The rsync is small, repeatable, and reversible (rollback =
rsync back, start the compose stack again).

## Cutover sequence

1. `terraform apply` podman-vm; verify mounts, linger, podman version.
2. Deploy traefik (staging ACME) + whoami. Test **from the LAN only** with
   `curl --resolve <host>:443:192.168.1.110` — no public change yet. Verify:
   staging wildcard issued, whoami serves, passthrough works against two or
   three legacy hostnames, **whoami shows the real client IP**.
3. Flip ACME to production, re-verify. Migrate authelia; verify a protected
   route via `--resolve`.
4. **Flip the front door:** OPNsense port-forward 80+443 (TCP and UDP)
   target changes `192.168.1.100` → `192.168.1.110`. Cloudflare, public DNS
   and cloudflare_ddns are untouched — they only know the WAN IP.
5. Soak. uptime_kuma (still on docker-1) now monitors every service through
   the new chain and alerts on breakage.

**Rollback at any moment:** flip the OPNsense forward back to `.100`.
Authelia is the only moved state; its rsync reverses. Nothing on docker-1 is
removed in this phase.

## Ops changes

- **Traefik access log** stays file-based under
  `/mnt/appdata/traefik/logs/` (fail2ban-style greppability, existing
  rotation habits). The logrotate postrotate becomes
  `systemctl --user -M ubuntu@ kill --signal=USR1 traefik` (root reaching
  into the user manager). The logrotate config moves from docker-vm's
  cloud-config to podman-vm's.
- Everything else logs to journald via systemd — `journalctl --user -u
  <name>` replaces `docker logs`.
- `podman-auto-update.timer` enabled for the ubuntu user.

## Success criteria

1. Production wildcard cert issued by the new traefik via DNS-01.
2. whoami reachable from the internet showing the **real client IP** in
   `X-Forwarded-For` (not pasta's gateway or the cloudflare edge).
3. Every legacy hostname serves correctly through TLS passthrough.
4. An authelia-protected route authenticates end-to-end.
5. `podman auto-update` updates whoami when its image tag moves.
6. A full podman-vm reboot brings traefik, authelia and whoami back
   **unattended** — proves linger, `RequiresMountsFor` and quadlet ordering.
7. Rollback rehearsed once: forward flipped back to `.100`, all services
   verified working the old way, then flipped forward again.
