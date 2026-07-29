# Paperless-ngx 3.0 — Design

**Date:** 2026-07-29
**Status:** Approved

## Goal

Add Paperless-ngx as a new service on docker-1, reachable at
`paperless.mercantus.ch`, to try out the 3.0 release (document archive with
OCR, full-text search and Office/email ingestion).

## Out of scope

- Podman. This is a docker-1 service; `podman/` is not touched, including the
  `legacy-docker1.yml` SNI passthrough list. Adding paperless there is the
  migration's problem, not this change's.
- DNS. The zone already has a wildcard record, so no Cloudflare change.
- Authelia SSO. Paperless has its own user system and token auth; a
  forward-auth gate in front of it breaks the mobile app, the REST API and any
  scanner integration. Paperless's own login is the gate.
- AI features (new in 3.0). Env-var-only to enable later; there is no active
  ollama service to point them at (`docker/_archive/ollama`).
- Migrating documents in from anywhere. Fresh, empty instance.

## What 3.0 changes

3.0.0 shipped 2026-07-22; 3.0.4 is current. Relevant to a fresh deployment:

| Change | Consequence here |
|---|---|
| `PAPERLESS_SECRET_KEY` is mandatory | Container refuses to start if unset or left at `change-me`. New `.env` entry |
| Whoosh → Tantivy search backend | Index lives under the data dir; rebuildable, so it belongs on the fast pool |
| Upstream compose moved to valkey 9 + postgres 18 | Follow it; postgres 18 volumes `/var/lib/postgresql`, not `/var/lib/postgresql/data` as in the 17 image outline uses |
| API v1 and API < 9 removed, python 3.10 dropped, encryption removed, pre/post-consume script positional args removed | None — nothing existing to break |
| Upgrades supported only from 2.20.15 | None — fresh install |

## Layout

One new directory, `docker/services/paperless/docker-compose.yml`.
`manage.py` discovers services by scanning `docker/services/*/docker-compose.yml`,
so no registration step exists: `python3 manage.py start paperless` works as
soon as the file does.

Five containers on two networks. Only the webserver joins `traefik-public`;
the rest are reachable only on a private `paperless_net`.

| Service / container | Image | Notes |
|---|---|---|
| `paperless` | `ghcr.io/paperless-ngx/paperless-ngx:3.0.4` | webserver + consumer + worker + scheduler under s6 |
| `db` / `paperless_db` | `postgres:18` | |
| `broker` / `paperless_broker` | `valkey/valkey:9-alpine` | speaks the redis protocol |
| `gotenberg` / `paperless_gotenberg` | `gotenberg/gotenberg:8.34` | office → PDF |
| `tika` / `paperless_tika` | `apache/tika:latest` | stateless; upstream tracks latest |

Inter-container addressing uses container names (`paperless_db`,
`paperless_broker`, …), matching how outline and nextcloud already do it.

## Version pinning — a deliberate break from the repo pattern

Most services here carry `com.centurylinklabs.watchtower.enable=true`; six
already do not — `arr-stack`, `hugo`, `immich`, `nextcloud`, `outline`,
`penpot`. Paperless joins that group deliberately, not as a precedent: its
images are pinned and it does not carry the label either.

Watchtower runs with `WATCHTOWER_LABEL_ENABLE=true`, so omitting the label is
sufficient — no `enable=false` needed.

Reasoning: paperless runs irreversible schema migrations on upgrade, and
3.0.2 exists solely to repair a migration broken in 3.0.1. An unattended 04:00
Monday pull that walks a document archive across a bad migration is the one
place in this repo where auto-update can cost data. `nextclouddb` is already
pinned for a comparable reason.

Upgrade path becomes: read the release notes, bump the tag, `python3 manage.py
update paperless`. With pinned tags the `docker compose pull` inside `update`
is a no-op until the tag changes — except for `apache/tika:latest`, which is
not pinned and will move on every pull regardless.

## Storage

Split along the boundary `.templates/env.template` documents — `DOCKERDIR`
(`/mnt/appdata`, SSD) for state and databases, `DATADIR` (`/mnt/main/data`,
bulk) for documents:

| Host path | Container path | Why |
|---|---|---|
| `${DOCKERDIR}/paperless/data` | `/usr/src/paperless/data` | Tantivy index, classifier model — rebuildable, latency-sensitive |
| `${DOCKERDIR}/paperless/db` | `/var/lib/postgresql` | postgres 18 volume location |
| `${DOCKERDIR}/paperless/redisdata` | `/data` | task queue |
| `${DATADIR}/paperless/media` | `/usr/src/paperless/media` | the documents — irreplaceable, bulk |
| `${DATADIR}/paperless/consume` | `/usr/src/paperless/consume` | drop folder |
| `${DATADIR}/paperless/export` | `/usr/src/paperless/export` | `document_exporter` target |

No manual `mkdir`/`chown` step. The container starts as root, remaps its
`paperless` user to `USERMAP_UID`/`USERMAP_GID`, then creates and chowns
data/media/consume/export — so the root-owned directories docker creates for
missing bind-mount sources are fixed on first start
(`s6-rc.d/init-modify-user`, `s6-rc.d/init-folders`).

## Configuration

New entries in `.env` (gitignored, edited on the host) and as placeholders in
the tracked `.templates/env.template`:

| Variable | Generation |
|---|---|
| `PAPERLESS_SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `PAPERLESS_DB_PASSWORD` | `openssl rand -base64 32` |
| `PAPERLESS_ADMIN_USER` | chosen |
| `PAPERLESS_ADMIN_PASSWORD` | chosen |

Set in the compose file, with the non-obvious ones justified:

- `PAPERLESS_URL=https://paperless.${HOST_DOMAIN}` — one setting that covers
  ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS and CORS_ALLOWED_HOSTS.
- `PAPERLESS_ALLAUTH_TRUSTED_CLIENT_IP_HEADER=CF-Connecting-IP` — allauth
  rate-limits logins per client IP. Behind traefik every request otherwise
  carries the same container IP, so a handful of failed logins from one client
  would lock out everyone. All traffic is Cloudflare-proxied
  (`cloudflare_ddns` runs `PROXIED=true`).
- `PAPERLESS_OCR_LANGUAGE=deu+eng` — the image ships eng/deu/ita/spa/fra, so
  no `PAPERLESS_OCR_LANGUAGES` install is needed.
- `PAPERLESS_TIME_ZONE=${TZ}`, `USERMAP_UID=${PUID:-1000}`,
  `USERMAP_GID=${PGID:-1000}`.
- `PAPERLESS_TIKA_ENABLED=1` plus the gotenberg (`:3000`) and tika (`:9998`)
  endpoints.
- `PAPERLESS_ADMIN_USER`/`PASSWORD` — applied by `init-superuser` only while
  no such superuser exists.

Gotenberg keeps upstream's hardening flags (`--chromium-disable-javascript=true`,
`--chromium-allow-list=file:///tmp/.*`) so `.eml` conversion cannot fetch
tracking pixels or run scripts.

## Routing

Labels mirror stirling-pdf: `traefik.enable=true`,
`traefik.docker.network=traefik-public`, `websecure` entrypoint, `cloudflare`
certresolver, ``Host(`paperless.${HOST_DOMAIN}`)``, service port 8000, scheme
http. No middlewares.

## Health and ordering

`db` gets a `pg_isready` healthcheck, `broker` a `valkey-cli ping`; the
webserver `depends_on` both with `condition: service_healthy`, and on
gotenberg/tika with `condition: service_started`. The paperless image ships its
own `HEALTHCHECK` against `localhost:8000`, so none is defined for it.

## Backups

Documents land on `${DATADIR}` (`/mnt/main`), which per
`.resources/infrastructure.md` has no recurring backup job and no offsite
copy. The postgres database, which lives on `${DOCKERDIR}`, holds every tag,
correspondent and title; losing it while `media/` survives leaves a folder of
unlabelled PDFs with none of paperless's organization intact. The `export`
mount exists for `document_exporter`, but nothing currently invokes it on a
schedule. This is accepted for a trial deployment and is the obvious
follow-up if paperless is kept.

## Verification

1. `python3 manage.py start paperless` on docker-1.
2. All five containers up; `paperless` reaches `healthy`.
3. `https://paperless.mercantus.ch` serves the login page over a valid
   certificate, and the bootstrap admin can log in.
4. A PDF dropped into `${DATADIR}/paperless/consume` is ingested, OCR'd, and
   findable by a word from its body via search.
5. A `.docx` dropped into the same folder is ingested — proves the tika and
   gotenberg path.
6. `docker compose logs paperless` shows no `[init-folders]` permission
   warnings.
