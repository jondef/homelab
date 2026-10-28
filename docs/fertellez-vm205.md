# fertellez staging — VM 205

Staging host for the fertellez product of Mercantus (repo `Mercantus/fertellez`). Cloned from VM 204
(velacasa) on 2026-10-28 and prepared with `docs/fertellez-vm205/prep205.sh`. Nothing of velacasa runs here.

| Item | Value |
|---|---|
| Proxmox VM | `205`, name `fertellez`, same shape as 204 (4 cores, 6000 MB, 50 GB on `local-zfs`, `onboot: 1`, guest agent on) |
| Hostname | `fertellez` |
| Address | `192.168.1.105/24` on `vmbr1`, static in the guest (`/etc/netplan/01-static.yaml`), gateway and DNS `192.168.1.1` |
| OS | Ubuntu 24.04 LTS, Docker, Compose v2 (inherited from 204) |
| Access | `ssh jon@192.168.1.105` (same key as 204; `jon` is in the `docker` group; `sudo` asks for a password) |

`.105` follows the "VM id minus 100" rule and stays below `.128` for Tailscale's `192.168.1.0/25`.

## Prep of the clone (`docs/fertellez-vm205/prep205.sh`)

Run once as root with the NIC link-down, as for 204. It removes the velacasa containers, images, volumes,
checkout and port guard; sets the hostname and the static address; regenerates `machine-id` and the SSH host
keys; installs `fertellez-port-guard` (TCP 3000 only from docker-1, IPv6 dropped). Then bring the link up
and reboot once. Clients that knew 204's host key under `.105` would complain; nothing does.

## Deploy

```sh
ssh jon@192.168.1.105
git clone git@github.com:Mercantus/fertellez.git ~/fertellez   # read-only deploy key; see below
cd ~/fertellez && cp .env.example .env.staging && chmod 600 .env.staging   # then fill POSTGRES_PASSWORD, APP_DB_PASSWORD, WEB_BIND=192.168.1.105, WEB_PORT=3000
deploy/staging.sh
```

The product repo's `deploy/README.md` documents the script and the post-deploy checks (forwarded hops from two
networks, footer SHA, noindex header).

## Ingress (docker-1 Traefik)

`docker/infrastructure/traefik/dynamic/fertellez.yml`, copied to `/mnt/appdata/traefik/dynamic/` on docker-1:
`fertellez.mercantus.ch` → `http://192.168.1.105:3000`, wildcard certificate, `X-Robots-Tag: noindex`. No
Authelia: the site has no login. When fertellez.mx exists: a Cloudflare zone, a second router (or a rename)
and the noindex middleware removed.

## Open

- Deploy key: the clone above uses jon's personal key the first time; replace with a read-only deploy key.
- Production: its own VM and fertellez.mx, with registry images (`compose.prod.yaml`).
