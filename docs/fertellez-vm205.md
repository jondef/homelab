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
Authelia: the app has its own sign-in.

`docker/infrastructure/traefik/dynamic/fertellez-com.yml`: `fertellez.com` → the same `fertellez-web` service,
`www.fertellez.com` → 301 to `https://fertellez.com/<path>`, one certificate for both from the `cloudflare` resolver.
No Traefik noindex: the app sends its own while `SEARCH_INDEXING=block`. Installed only once the zone is Active
(below).

## fertellez.com

Registered at Wix (a Wix site serves it today); the transfer out started 2026-11-07 (`pendingTransfer` at the
registry). Its DNS is still Wix's (`ns6`/`ns7.wixdns.net`) and it carries **Google Workspace mail**: whatever moves
the DNS must keep the mail records, or mail to `@fertellez.com` stops. Public records on 2026-11-08: apex A
`185.230.63.107/.171/.186` and `www` CNAME `cdn3.wixdns.net` (the Wix site), MX `10 aspmx.l.google.com`, TXT
`v=spf1 include:_spf.google.com ~all`, TXT `google-site-verification=…`, `_dmarc` CNAME `_dmarc.wixemails.com`.
No DS record, so no DNSSEC to undo.

OPNsense's 80/443 forward admits only Cloudflare's ranges, so the domain must be a proxied Cloudflare zone; an A
record at Wix pointing at the WAN address would be dropped.

1. **Now, while the transfer runs.** Cloudflare, same account as `mercantus.ch`: add the site `fertellez.com`
   (Free). The scan imports Wix's records; make the zone exactly this:

   | Type | Name | Content | Proxy |
   |---|---|---|---|
   | CNAME | `@` | `mercantus.ch` (flattened; follows the DDNS-updated WAN address) | Proxied |
   | CNAME | `www` | `mercantus.ch` | Proxied |
   | MX | `@` | `aspmx.l.google.com`, priority 10 | DNS only |
   | TXT | `@` | `v=spf1 include:_spf.google.com ~all` | |
   | TXT | `@` | the `google-site-verification=…` value, as is | |
   | TXT | `_dmarc` | `v=DMARC1; p=none` (replaces the CNAME to Wix's reporting) | |

   Delete the imported Wix A records and the `www` CNAME to `wixdns.net`. Before the switch, compare with Wix's
   own DNS panel (Domains → fertellez.com → DNS records): public DNS does not list every name, such as a DKIM
   selector or a subdomain. SSL/TLS → **Full (strict)**. Note the two nameservers Cloudflare assigns.
   Traefik's `CLOUDFLARE_DNS_API_TOKEN` (docker-1 `.env`) must reach the zone: "All zones" does; a token
   limited to listed zones needs `fertellez.com` added (Zone Read, DNS Edit), or the certificate never issues.
2. **When the transfer completes.** The registry refuses nameserver changes while `pendingTransfer`; a `.com`
   transfer is auto-approved after five days, so by about 2026-11-12. At the new registrar, set the nameservers to
   the two Cloudflare ones. Wait for the zone to show **Active** (resolvers may keep asking Wix for up to 48 h,
   the `.com` delegation TTL; they see the old site meanwhile).
3. **Route.** On docker-1, copy `fertellez-com.yml` to `/mnt/appdata/traefik/dynamic/`. The file provider picks it
   up and Traefik requests the certificate; `docker logs traefik 2>&1 | grep -i fertellez.com` shows an ACME error
   if the token or the zone is wrong. After fixing either, `touch` the file to retry.
4. **Check.** `curl -sI https://fertellez.com` answers 200 (a 526 is Traefik without its certificate);
   `curl -sI https://www.fertellez.com/contacto` answers 301 to `https://fertellez.com/contacto`;
   `dig +short MX fertellez.com @1.1.1.1` shows Google; a mail to a `@fertellez.com` mailbox arrives.

Rollback: delete the file on docker-1; the site stays on `fertellez.mercantus.ch`. Mail depends only on the zone's
MX and TXT records.

After step 4 the site answers on both hosts. The rest is the product repo's: `PASSKEY_RP_ID` and `PASSKEY_ORIGIN`
in `.env.production` (passkeys, the CSRF origin and Stripe's return links stay on `fertellez.mercantus.ch` until
they change; admins then register passkeys again), the canonical `metadataBase`, `SEARCH_INDEXING`, the Stripe
webhook URL. Only after those can `fertellez.mercantus.ch` redirect to `fertellez.com`.

## Open

- Deploy key: the clone above uses jon's personal key the first time; replace with a read-only deploy key.
- Production: its own VM and fertellez.mx, with registry images (`compose.prod.yaml`).
