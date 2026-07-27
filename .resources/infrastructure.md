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
        ┌─────────────────┬────────────┼────────────┬──────────────────┐
        │                 │            │            │                  │
  proxmox host    OPNsense VM 200   CT 100    windows-sandbox 998
  192.168.0.5      (WAN leg)      192.168.0.3   (dual-homed, stopped)
                        │          tailscale
                   routes / NATs   + pihole
                        │              │
                      vmbr1  ──────────┘        "inside" bridge
                 192.168.1.0/24                  bridge-ports: none
                 gw 192.168.1.1                   (purely virtual)
                        │
   ┌────────────┬───────┴────┬─────────────┬──────────────┬─────────────┐
   │            │            │             │              │             │
docker-1 201  CTdeM 202  faktura24 203  vdi 999   CT 101 minecraft  proxmox host
192.168.1.100                                     192.168.1.69      192.168.1.5
                                                                    CT 100 .1.3
```

Two things straddle both bridges: **OPNsense** (the router) and **CT 100**
(Tailscale + DNS). That second one matters — it is why remote access does not
depend on OPNsense.

**The important distinction:** `vmbr0` owns the physical NIC (`enp4s0`) and
carries the host's default route. `vmbr1` has `bridge-ports none` — it is a
purely virtual switch with no path off the box except through OPNsense, which
straddles both bridges and acts as the router for `192.168.1.0/24`.

So every service VM sits behind OPNsense. The Proxmox host keeps a leg on both
(`192.168.0.5` and `192.168.1.5`), which is how it reaches guests directly.

---

## What the upstream router forwards

Two different destinations — the web ports and the VPN port take separate paths:

```
TCP+UDP  80, 443   ──►  OPNsense (WAN leg on vmbr0) ──►  docker-1 :80/:443
                        └─ firewall: ONLY cloudflare source IPs pass,
                           everything else is dropped

UDP      41641     ──►  CT 100 ubuntu-vpn-dns (192.168.0.3)  — bypasses OPNsense
```

**80/443 are forwarded for TCP *and* UDP.** The UDP half carries HTTP/3 (QUIC);
without it clients silently fall back to TCP.

**OPNsense drops anything that is not a Cloudflare source IP** on those ports. So
the origin is not just hidden behind Cloudflare's proxy — it is unreachable
directly even by someone who learns the address. That closes the
direct-to-origin bypass that proxying alone would leave open.

**The Tailscale port goes straight to CT 100**, not through OPNsense, because
that container has its own leg on `vmbr0` at `192.168.0.3`. Forwarding it is not
required for Tailscale to function, but it lets peers negotiate a **direct**
connection instead of relaying through a DERP server — noticeably faster from
abroad.

Nothing else is forwarded. SSH, the Proxmox UI and Gitea's SSH on 222 are
reachable only once you are on the tailnet.

---

## Ingress: how a request reaches a service

```
https://<name>.mercantus.ch
   │
   ▼   DNS resolves to Cloudflare, not to us — the records are proxied
Cloudflare edge  (104.21.x / 172.67.x)
   │
   ▼   :443 → home router → OPNsense → docker-1
traefik (container, owns :80 and :443)
   │   matches Host(`<name>.mercantus.ch`) from docker labels
   │   optionally through the authelia@docker forward-auth middleware
   ▼
service container, reached over the traefik-public docker network
```

- **Traffic is proxied through Cloudflare.** Public DNS returns Cloudflare
  addresses, so the home IP is not published. `cloudflare_ddns` keeps the origin
  record pointed at the current WAN address behind that.
- Because every request then arrives *from* Cloudflare, Traefik is configured
  with `--entrypoints.*.forwardedHeaders.trustedIPs=<cloudflare ranges>`. Without
  it Traefik would treat the Cloudflare edge as the client and overwrite
  `X-Forwarded-For`, so every service would log, rate-limit and geo-locate
  Cloudflare instead of the actual visitor.
- **Only 80/443 are open to the internet.** Everything else — SSH, the Proxmox
  UI, Gitea's SSH on 222 — is reachable over Tailscale only.
- **Certificates** are a wildcard (`mercantus.ch` + `*.mercantus.ch`) from
  Let's Encrypt via the `cloudflare` resolver using a **DNS-01** challenge, so no
  inbound port is needed to issue or renew them. State lives in
  `/mnt/appdata/traefik/acme.json`.

Note that proxying alone would only *hide* the origin — anyone who discovered
the address could still connect directly and bypass Cloudflare's WAF and rate
limiting. **OPNsense closes that** by dropping any source outside Cloudflare's
ranges on 80/443, so the proxy is not merely cosmetic.
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

## Remote access and DNS

Both live in **CT 100 `ubuntu-vpn-dns`**, an unprivileged LXC container — not on
the Proxmox host, not on OPNsense, and not on docker-1. Like OPNsense it is
dual-homed, which is the whole trick:

```
net0  vmbr0   192.168.0.3/24    ← outside; the 41641/UDP forward lands here
net1  vmbr1   192.168.1.3/24    ← inside
ip_forward=1
```

Having a leg on both bridges is why it can route to everything without
traversing OPNsense, and why the VPN port can be forwarded straight to it.

- **Tailscale** advertises `192.168.0.0/25` and `192.168.1.0/25` as subnet
  routes. ⚠️ Those are **/25, not /24** — only `.0`–`.127` of each subnet is
  reachable over the tailnet. Everything current sits inside that range
  (docker-1 `.100`, host `.5`, minecraft `.69`), but anything you place at
  `.128` or above would be invisible from outside and the reason would be
  non-obvious.
- **Pi-hole** (`pihole-FTL`) serves DNS on `:53` — the other half of the name.

Practical consequence: from away, use IP addresses. LAN hostnames resolve only
at home — `k8` is a shell alias for `ssh ubuntu@192.168.1.100`, not DNS.

---

## Storage

### Pools

```
rpool       2 × 1 TB NVMe mirror      930 GB    proxmox root, VM disks (zvols), databases
main_pool   2 × 20 TB HDD mirror      18.2 TB   bulk: photos, documents, media
sdc         250 GB SATA SSD           —         EFI partition only (see below)
```

Both pools are imported by the **host**. `main_pool` used to be disk-passthrough'd
into docker-1, which trapped 18 TB inside a single VM and made it unreachable by
anything else. It now belongs to the host and is shared out, so the data outlives
any VM — proved when docker-1 was destroyed and rebuilt with `main_pool` untouched.

### The rule: block device for databases, file share for bulk

ZFS presents storage two ways, and picking the right one matters more than
picking the right pool:

```
zvol      a raw block device   → attached as a VM disk → guest formats it (ext4)
dataset   a filesystem         → shared into the VM over virtiofs
```

Databases need low latency and a real `fsync`, so they get a zvol. Bulk files are
perfectly happy on a share. Measured on this hardware with incompressible data:

```
                    NVMe zvol   virtiofs   host-native ZFS
seq write (fsync)    448 MB/s   129 MB/s      130 MB/s
create 2000 files     14634/s      561/s        6221/s
```

Sequential throughput over virtiofs is **free** — 129 vs 130 MB/s, so the HDDs
are the bottleneck, not the share. Metadata is ~11× slower than native, which is
precisely why no database is allowed there. virtiofs is a shared-memory
transport, not a network filesystem; it replaced an NFS export that was slower
and added a network dependency between two machines that are really one.

### What lives where

```
/mnt/appdata   100 GB zvol on rpool, ext4   ${DOCKERDIR}   app state + every database
/mnt/main      virtiofs from main_pool      ${DATADIR}     nextcloud, immich, downloads, unsorted
```

Compose files reference these only through `${DOCKERDIR}` and `${DATADIR}` in
`.env`, so the entire tiering is two variables rather than a hundred hard-coded
paths. Immich shows the split clearly: its photo library resolves under
`${DATADIR}` on spinning disk, its Postgres under `${DOCKERDIR}` on NVMe.

### Operational notes

- **ARC is capped at 32 GB** on the host (`/etc/modprobe.d/zfs.conf`). The cache
  lives wherever the pool is *imported*, so moving `main_pool` to the host moved
  that RAM budget with it — docker-1 was shrunk 64 → 32 GB to pay for it.
- **Scrubs** run the second Sunday monthly (`/etc/cron.d/zfsutils-linux`) across
  every imported pool. Both currently scrub clean with zero errors.
- **Compression is on** for both pools, so `du` reports compressed size. Expect
  data restored onto an uncompressed filesystem to look noticeably larger.
- **Backups:** one manual `zfs send` of `/mnt/appdata` sits at
  `main_pool/backup/vm-201-appdata`. It has been restored from successfully, so
  the path is proven — but there is **no recurring job yet**, and no offsite copy.

### Boot caveat

The EFI partition lives on **sdc**, a single SATA SSD — not on the NVMe mirror,
which is entirely consumed by ZFS with no room for an ESP. Proxmox itself
(`rpool/ROOT/pve-1`) is mirrored and safe.

If sdc dies: **no data is lost, but the host will not boot** until an ESP is
recreated on another disk. That is a downtime risk, not a data risk, and fixing
it requires someone physically present.

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
