# Velacasa staging — VM 204

Staging host for the Velacasa product of Mercantus (repo `Mercantus/mercantus-airbnb`). Set up on
2026-10-18 by cloning VM 203 (faktura24) and cleaning the clone; nothing of faktura24 runs here.

| Item | Value |
|---|---|
| Proxmox VM | `204`, name `velacasa`, 4 cores, 6000 MB, 50 GB on `local-zfs`, `onboot: 1`, guest agent on |
| Hostname | `velacasa` |
| Address | `192.168.1.104/24` on `vmbr1`, **static in the guest** (`/etc/netplan/01-static.yaml`), gateway `192.168.1.1`, DNS `192.168.1.1` |
| OS | Ubuntu 24.04.4 LTS, Docker 29.5.2, Compose v5.1.4 |
| Access | `ssh jon@192.168.1.104` (same key as VM 203; `jon` is in the `docker` group; `sudo` asks for a password). LAN or tailnet only, nothing is forwarded to it |

Why `.104`: the static addresses of service VMs follow "VM id minus 100" (`201 → .100`, `210 → .110`),
and the DHCP leases on this subnet sit in the .50–.99 range, so a static address there could collide
with a future lease. Must stay below `.128` because Tailscale advertises `192.168.1.0/25`.

## What was done on the clone (2026-10-18)

Done through `qm guest exec` with the NIC `link_down=1`, so the clone never appeared on the network
with faktura24's identity. Script kept at `/root/prep204.sh` on the VM.

1. Every container, image, network and named volume of faktura24 removed (`docker system prune -a --volumes`
   plus `docker volume rm` for the named ones; 3.7 GB reclaimed).
2. Hostname `faktura24` → `velacasa` (`hostnamectl`, `/etc/hosts`).
3. DHCP replaced by the static address above; the subiquity file is backed up in `/root/netplan-backup/`.
4. New `/etc/machine-id` and new SSH host keys (the clone shared both with VM 203, which breaks DHCP
   leases and makes the two hosts indistinguishable to SSH clients).
5. Link brought back up (`qm set 204 --net0 virtio=BC:24:11:B3:DD:68,bridge=vmbr1,firewall=1`).

Nothing of faktura24 is left on the disk: `/home/jon/faktura24` (the checkout with its `.env` files) was
deleted on 2026-10-18 after Armando's ok.

## Next: deploy

The product repo ships `compose.prod.yaml` and `make prod` (requires `IMAGE_TAG` and `.env.production`).
Planned path, not done yet:

- Checkout or image pull on the VM, `make prod` with the production env file kept only on the VM.
- Ingress through docker-1's Traefik (file provider, like `docs/koha-eval-vm202.md` §5) pointing at
  `http://192.168.1.104:8080` (web), under a `*.mercantus.ch` name or the product's own domain once it
  exists; Cloudflare in front as for every other service.
- The API is never published directly: nginx in the `web` container proxies `/api/` to the `api` container.

## Access gate: Authelia (2026-10-18)

The staging accepts the fixed login code `000000` for every seeded account (product ADR-0010), so the
whole site sits behind Authelia's forward auth. Authelia's cookie for `mercantus.ch` never reaches
`velacasa.app`, so the portal has its own address under the protected domain:

| Piece | Where |
|---|---|
| DNS | `auth.velacasa.app` CNAME → `mercantus.ch`, proxied (created through the Traefik token) |
| Authelia | `/mnt/appdata/authelia/config/configuration.yml`: a second `session.cookies` entry for `velacasa.app` with `authelia_url: https://auth.velacasa.app`, and `access_control` rules `velacasa.app` + `*.velacasa.app` → `one_factor`. Backup: `configuration.yml.bak-2026-10-18`. Validated with `authelia config validate` before the restart |
| Traefik | `docker/infrastructure/traefik/dynamic/velacasa.yml`: middleware `velacasa-auth` (`/api/authz/forward-auth`) on the `velacasa` router, router `velacasa-auth-portal` for `auth.velacasa.app` → `http://authelia:9091` |

Every Authelia user can enter (one factor). To give the pilot agency access, add them to
`users_database.yml`; to restrict, change the `velacasa.app` rules to a group.

Check: `curl -sI https://velacasa.app` answers `302` to `https://auth.velacasa.app/?rd=…`.

## Port guard (2026-10-18)

The Proxmox firewall is disabled at datacenter level, so the restriction lives inside the VM: a
`DOCKER-USER` rule (the chain Docker leaves to the administrator for published ports) admits TCP 8080
only from docker-1 and drops every other source on `enp6s18`. Without it any LAN or tailnet host could
open `http://192.168.1.104:8080` and bypass the Authelia gate, and could spoof `X-Forwarded-For`.

- Covers IPv4 (allow docker-1, drop the rest) and IPv6 (drop all; Docker publishes on `[::]` too and link-local addresses are reachable on the same switch).
- Script `/usr/local/sbin/velacasa-port-guard` (idempotent), unit `velacasa-port-guard.service`
  (`After=docker.service`, enabled). Check with `sudo iptables -S DOCKER-USER`.
- If docker-1 ever changes address, edit `ALLOW=` in the script and restart the unit.
