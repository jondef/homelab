# fertellez production — VM 205

Production host (staging until 2026-10-31) for the fertellez product of Mercantus (repo `Mercantus/fertellez`). Cloned from VM 204
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

`docker/infrastructure/traefik/dynamic/fertellez-com.yml`, copied to `/mnt/appdata/traefik/dynamic/` on docker-1:
`fertellez.com` → `http://192.168.1.105:3000` (the `fertellez-web` service, defined in the same file),
`www.fertellez.com` → 301 to `https://fertellez.com/<path>`, one certificate for both from the `cloudflare` resolver.
No Authelia: the app has its own sign-in. No Traefik noindex: the app sends its own while `SEARCH_INDEXING=block`.

`fertellez.mercantus.ch` was the first host (2026-10-28 to 2026-11-16, `fertellez.yml`, with a Traefik noindex). It
was removed once fertellez.com was in Cloudflare and `PASSKEY_ORIGIN` had moved there (passkeys and the CSRF check no
longer worked on it). `fertellez.yml` used to define `fertellez-web`; never put it back next to `fertellez-com.yml`:
a service defined in two files of the provider is dropped from both, and the site goes down.

Swapped on docker-1 on 2026-11-17 01:22 UTC (backups `~/fertellez-com.yml.bak-20261116` and `~/fertellez.yml.bak-20261116`
of user `ubuntu`, who is the SSH login there), in one step, so no moment has the service twice or not at all:

```sh
cd /mnt/appdata/traefik/dynamic
cp fertellez-com.yml ~/fertellez-com.yml.bak && cp fertellez.yml ~/fertellez.yml.bak
cp <homelab checkout>/docker/infrastructure/traefik/dynamic/fertellez-com.yml /tmp/fertellez-com.yml
mv /tmp/fertellez-com.yml fertellez-com.yml && rm fertellez.yml
```

Rollback: put both backups back (`mv` the new `fertellez-com.yml` out first).

## fertellez.com

Registered at Wix until the transfer (started 2026-11-07); the zone is in **Cloudflare** since 2026-11-16, same
account as `mercantus.ch`, nameservers `*.ns.cloudflare.com`. It carries **Google Workspace mail**: whatever changes the
zone keeps the mail records, or mail to `@fertellez.com` stops. Public records on 2026-11-20:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A/CNAME | `@` | the homelab (answers with Cloudflare addresses) | Proxied |
| A/CNAME | `www` | the homelab | Proxied |
| MX | `@` | `aspmx.l.google.com`, priority 10 | DNS only |
| TXT | `@` | `v=spf1 include:_spf.google.com ~all` | |
| TXT | `@` | the `google-site-verification=…` value | |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:info@fertellez.com` | |
| TXT | `google._domainkey` | the Google Workspace DKIM key (`v=DKIM1; k=rsa; …`) | |

No `_acme-challenge` record: Traefik writes a temporary TXT there for each issuance and removes it. SSL/TLS →
**Full (strict)**.

OPNsense admits 80/443 only from Cloudflare's ranges (`.resources/infrastructure.md`), so both names must stay
proxied: a grey-cloud record would point visitors at an address that drops them. Checked 2026-11-16 from a network
outside the homelab: straight to the WAN address, 80 and 443 time out; through Cloudflare, `https://fertellez.com`
answers 200 and `www` answers 301.

**Certificate.** Let's Encrypt via DNS-01 in the fertellez.com zone itself. The zone came over from Wix with a
**proxied** CNAME `_acme-challenge.fertellez.com` → `_acme-challenge.fertellez-com.mercantus.ch` (the delegation used
while the DNS was at Wix). Proxied, it is invisible to `dig` from outside, and Cloudflare refuses a TXT next to a
CNAME, so it would have broken the apex renewal; it was deleted on 2026-11-20. Read the record list in the dashboard,
not with `dig`, when checking the zone. The certificate in use was issued 2026-11-09 (through that delegation) and is
valid until 2027-02-07; Traefik renews about 30 days before, around 2027-01-08, now in this zone. It needs Traefik's
`CLOUDFLARE_DNS_API_TOKEN` to reach `fertellez.com` (Zone Read, DNS Edit).

Proven on 2026-11-20 after the deletion: a temporary router for `acme-wild.fertellez.com` requesting `*.fertellez.com`
(file `zz-acme-wild.yml`, `service: noop@internal`, deleted afterwards) got its certificate in under two minutes. A
wildcard challenge uses `_acme-challenge.fertellez.com`, the same name as the apex renewal; a test with a subdomain
(`acme-test.fertellez.com`, 2026-11-17) uses another name and does not prove it. Repeat the wildcard test after any
change to the token or the zone. `docker logs traefik 2>&1 | grep -i fertellez.com` shows an ACME error if not. Check the expiry with
`echo | openssl s_client -connect 192.168.1.100:443 -servername fertellez.com 2>/dev/null | openssl x509 -noout -enddate`.

## Open

- Deploy key: the clone above uses jon's personal key the first time; replace with a read-only deploy key.
- A registry for the images (product ADR-0002); until then they are built on the VM.
