# Infrastructure overview

How this homelab is wired, with an emphasis on networking. Companion to
`proxmox.md`, which holds the runbook commands.

---

## Topology

```
                          Internet
                             │   only :80 and :443 are exposed
                             ▼
                     192.168.0.1   upstream router
                             │
              enp4s0 ────────┴──────── vmbr0        "outside" bridge
                                        │            (has the physical NIC)
              ┌─────────────────────────┼──────────────────────┐
              │                         │                      │
     proxmox host                 OPNsense VM 200        windows-sandbox 998
     192.168.0.5                  (WAN leg)              (dual-homed)
                                        │
                                   routes / NATs
                                        │
                                      vmbr1           "inside" bridge
                                 192.168.1.0/24        bridge-ports: none
                                 gw 192.168.1.1         (purely virtual)
                                        │
        ┌───────────────┬───────────────┼───────────────┬──────────────┐
        │               │               │               │              │
   docker-1 201    CTdeM 202     faktura24 203    ubuntu-vdi 999   proxmox host
   192.168.1.100                                                   192.168.1.5
```

**The important distinction:** `vmbr0` owns the physical NIC (`enp4s0`) and
carries the host's default route. `vmbr1` has `bridge-ports none` — it is a
purely virtual switch with no path off the box except through OPNsense, which
straddles both bridges and acts as the router for `192.168.1.0/24`.

So every service VM sits behind OPNsense. The Proxmox host keeps a leg on both
(`192.168.0.5` and `192.168.1.5`), which is how it reaches guests directly.

---

## Ingress: how a request reaches a service

```
https://<name>.mercantus.ch
   │
   ▼  :443 forwarded to docker-1
traefik (container, owns :80 and :443)
   │  matches Host(`<name>.mercantus.ch`) from docker labels
   │  optionally through the authelia@docker forward-auth middleware
   ▼
service container, reached over the traefik-public docker network
```

- **Only 80/443 are open to the internet.** Everything else — SSH, the Proxmox
  UI, Gitea's SSH on 222 — is reachable over Tailscale only.
- **Certificates** come from Let's Encrypt via the `cloudflare` resolver using a
  DNS-01 challenge, so no inbound port is needed to issue them. State lives in
  `/mnt/appdata/traefik/acme.json`.
- **Authelia** publishes a forward-auth middleware through its own docker labels
  (`traefik.http.middlewares.authelia.forwardauth.*`). Routers opt in with
  `traefik.http.routers.<x>.middlewares=authelia@docker`.
- Traefik discovers everything by reading `/var/run/docker.sock`. It exposes
  nothing by default (`--providers.docker.exposedbydefault=false`); a container
  is only routed if it carries `traefik.enable=true`.

---

## Container networking

```
traefik-public   172.19.0.0/16   shared ingress net, joined by traefik + 19 services
gitea_git_net    172.22.0.0/16   per-stack private nets, one per compose project
immich_immich_net, nextcloud_nextcloud_net, penpot_penpot_net, ...
```

Each stack gets its own private network for app↔database traffic, and joins
`traefik-public` only if it needs to be routed. Databases are never on
`traefik-public`, so nothing outside their own stack can reach them.

`traefik.docker.network=traefik-public` on a container tells Traefik which of
its several networks to dial — without it, Traefik may pick the private one and
fail.

**Docker allocates from 172.17–172.30.** Keep it that way: an earlier build had
bridges in `192.168.16.x` and `192.168.48.x`, which risks colliding with LAN or
VPN subnets and silently blackholing traffic.

---

## Remote access

Tailscale is **not** installed on the Proxmox host or on docker-1. Both
`192.168.0.0/24` and `192.168.1.0/24` are reachable from outside, so something
advertises them as subnet routes — almost certainly the Tailscale plugin on
OPNsense. *(Inferred from routing behaviour, not verified directly.)*

Practical consequence: from away, use IP addresses. LAN hostnames (`k8` is a
shell alias, not DNS) resolve only at home.

---

## Storage, and why it is not networking

`/mnt/main` inside docker-1 looks like a network mount but is not. The 18 TB
pool is imported by the **host**, and shared into the VM over **virtiofs** — a
shared-memory transport, not a network filesystem.

```
host: main_pool/main_fs → /mnt/main ──virtiofs──► docker-1 /mnt/main
host: rpool zvol        ──virtual disk──────────► docker-1 /mnt/appdata (ext4)
```

Measured here: virtiofs costs ~0% on sequential throughput (129 vs 130 MB/s
native) but is ~11× slower on metadata. That is why databases live on the
NVMe-backed zvol (`/mnt/appdata`) and only bulk files use the share.

It replaced an NFS export, which was slower and added a network dependency
between two machines that are really one.

---

## Invariants worth not breaking

1. **Only 80/443 public.** Everything else goes over Tailscale.
2. **Databases stay off `traefik-public`.** They belong on per-stack networks.
3. **Docker keeps its `172.x` pool** — do not let it allocate in `192.168.x`.
4. **Anything mounting `docker.sock` is coupled to the Docker version.** Traefik
   and Watchtower both broke on the Docker 29 upgrade because their API clients
   were too old. Check those first after any Docker bump.
5. **`docker.service` requires its mounts** (`RequiresMountsFor=/mnt/main
   /mnt/appdata`). Without it, containers bind-mount empty directories and apps
   reinitialise into them.
