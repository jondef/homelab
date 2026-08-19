# Koha on VM 202 — evaluation runbook

Evaluation install of **Koha 26.05** (current stable) on the CTdeM test VM — Proxmox VM `202`, `192.168.1.59`, Ubuntu 24.04 — alongside the existing Docker test stack. Goal: the librarian evaluates cataloging, revistas (serials), circulation, and Drive-linked digital content. Nothing here is permanent: production later lands on the real CTdeM VM via `koha-dump` → `koha-restore` (step 8), or a clean re-install if the eval data is disposable.

## Decisions

| Topic | Decision |
|---|---|
| Koha | 26.05 line, official community packages (`stable` repo), **not** Docker |
| Instance name | `biblioteca` |
| Database | Dedicated MariaDB on the VM at 3306; the Docker MySQL moves to host port 3307 |
| OPAC (students) | Apache port **8081** → `https://biblioteca.mercantus.ch` via Traefik |
| Staff interface | Apache port **8082** → `https://biblioteca-admin.mercantus.ch` via Traefik |
| Digital content | Google Drive shared drive, domain-restricted; linked from MARC 856 fields |

Port collisions checked on the VM: 3000 (frontend), 5001 (backend), 3306 (MySQL container) are taken; 80, 8081, 8082 are free. Only 3306 needs handling.

## 1. Resize the VM (on the Proxmox host)

Koha + MariaDB + Zebra want ~2–3 GB on top of the existing stack; the VM has 2 GB. Memory change needs a stop/start.

```sh
ssh root@192.168.0.5
qm shutdown 202 && qm set 202 --memory 6144 --cores 4 && qm start 202
```

## 2. Move the Docker MySQL off host port 3306

The `db` service publishes `"3306:3306"`. Containers talk over the compose network, so the published port only serves host-side access — change it in the compose file the stack runs from on the VM:

```yaml
  db:
    ports:
      - "127.0.0.1:3307:3306"
```

```sh
docker compose up -d db
```

Anything that poked MySQL at `localhost:3306` from the host now uses `localhost:3307`. Side benefit: MySQL is no longer exposed to the LAN.

## 3. Run the install script

The install itself is scripted so the exact same procedure repeats on the production CTdeM VM later: **`scripts/install-koha.sh` in the CTdeM repo**. It is idempotent (safe to re-run), keeps Apache off port 80 entirely, aborts with instructions if 3306 is still taken, and prints the web-installer credentials at the end.

```sh
scp scripts/install-koha.sh jon@192.168.1.59:
ssh jon@192.168.1.59 sudo ./install-koha.sh
```

Defaults: instance `biblioteca`, OPAC 8081, staff 8082, suite `stable` (currently 26.05.x — `apt upgrade` then tracks monthly point releases and runs schema migrations automatically), translation `es-ES`. Override via env, e.g. `sudo KOHA_SUITE=26.05 ./install-koha.sh`.

**For the production run later:** pin `KOHA_SUITE` to the release line the eval ended up on — `koha-restore` requires matching versions (step 8).

## 4. Web installer

The script prints the initial login (the instance's DB user); to re-read it later:

```sh
sudo grep -A2 '<user>koha_biblioteca</user>' /etc/koha/sites/biblioteca/koha-conf.xml
```

Open `http://192.168.1.59:8082`, log in as `koha_biblioteca`, and run the installer:

- Language **es-ES**, marcflavour **MARC21**.
- Accept the offered **sample data** (libraries, patron categories, item types, circulation rules) — it makes the evaluation far faster than defining everything from scratch.
- The onboarding wizard at the end creates the real superlibrarian account; the `koha_biblioteca` DB login is never used interactively again.

Sanity check: OPAC responds at `http://192.168.1.59:8081`.

## 5. Publish through Traefik + Cloudflare

DNS: add `biblioteca` and `biblioteca-admin` records for `mercantus.ch`, same pattern as `ctdem`.

Traefik file provider, following the existing config's style:

```yaml
http:
  routers:
    biblioteca:
      rule: "Host(`biblioteca.mercantus.ch`)"
      entryPoints:
        - websecure
      tls:
        certResolver: cloudflare
      service: koha-opac

    biblioteca-admin:
      rule: "Host(`biblioteca-admin.mercantus.ch`)"
      entryPoints:
        - websecure
      tls:
        certResolver: cloudflare
      service: koha-staff

  services:
    koha-opac:
      loadBalancer:
        servers:
          - url: "http://192.168.1.59:8081"

    koha-staff:
      loadBalancer:
        servers:
          - url: "http://192.168.1.59:8082"
```

Then in the staff interface → Administration → Global system preferences:

- `OPACBaseURL` = `https://biblioteca.mercantus.ch`
- `staffClientBaseURL` = `https://biblioteca-admin.mercantus.ch`

During the eval, the staff interface is protected only by Koha's own login. Before real cataloging data goes in, either put `biblioteca-admin` behind Authelia / Cloudflare Access, or delete that router and reach 8082 over Tailscale only.

## 6. Digital content via Google Drive

1. In Workspace admin, create a **shared drive** named `Biblioteca CTdeM` (a shared drive, not a folder in someone's My Drive — files must survive staff turnover).
2. Members: library staff as Content managers. General access: **CTdeM domain only — Viewer**, link required. Never "anyone with the link" — the domain restriction *is* the access control.
3. Optional per file: "Viewers can't download, print, or copy" for honest-person protection.
4. Upload a sample revista PDF and copy its link.
5. In Koha staff → Cataloging → new record: fill in the basics (245 title, etc.) and field **856** (indicators `4 0`): `$u` = the Drive URL, `$y` = `Leer en línea`.
6. From the OPAC, the record shows the link under **Online resources**. Verify with a student Workspace account (opens) and a personal Gmail (denied).

## 7. Librarian evaluation checklist

- Catalog a physical book — prefer **Cataloging → New from Z39.50/SRU** to import a ready-made record instead of typing MARC by hand.
- Add an item with a barcode, create a patron, check the book out, check it in.
- **Serials:** create a subscription for one revista, set its prediction pattern (frequency), receive an issue, and look at the expected/arrived/late workflow — this is the feature Koha was chosen for.
- Open a Drive-linked digital record from the OPAC (step 6).
- Poke OPAC customization: library name, welcome text, language switching.

## 8. Backups and the eventual migration

The packages already run nightly dumps to `/var/spool/koha/biblioteca/` (2-day retention). Enough for the eval; start copying them off the VM before the librarian invests real cataloging time.

Migration to the production CTdeM VM = install the **same Koha version** there, then:

```sh
sudo koha-dump biblioteca      # writes .sql.gz + config .tar.gz to /var/spool/koha/biblioteca
# copy both files to the target machine, then there:
sudo koha-restore biblioteca.sql.gz biblioteca.tar.gz
```

plus the equivalent reverse-proxy config and a DNS flip. If the eval data turns out to be junk, a fresh install + web installer on the target is equally valid.

## Gotchas

- **Search returns nothing or stale results:** `sudo koha-rebuild-zebra -f -v biblioteca`.
- **Background jobs stuck** (imports sitting in "new"): `sudo systemctl restart koha-common` restarts Zebra, Plack, and the workers for all instances.
- **After `apt upgrade` of koha-common** the staff interface may show a maintenance page briefly while schema migrations run — normal.
- **Memory pressure:** watch `free -m`; if the MySQL container + MariaDB + Koha squeeze, bump the VM to 8 GB.
- **`koha-translate` warns "Connection to the memcached servers '__MEMCACHED_SERVERS__' failed":** cosmetic — the translate tool reads the config *template*; the instance's real koha-conf.xml gets proper values from koha-sites.conf. Verify memcached with `ss -tln | grep 11211`.
- **`koha-create` aborts with "Koha requires mod_cgi":** `a2enmod cgi` under the default threaded MPM silently enables `cgid`, which the check rejects. The install script enables cgi only after koha-common switches Apache to mpm_itk/prefork (fixed in `scripts/install-koha.sh`).
