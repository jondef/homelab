# Paperless-ngx 3.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Paperless-ngx 3.0.4 on docker-1 at `https://paperless.mercantus.ch`, with Office/email ingestion and German+English OCR.

**Architecture:** One new auto-discovered compose stack at `docker/services/paperless/docker-compose.yml` — five containers (paperless webserver, postgres 18, valkey 9, gotenberg, tika) across two networks, where only the webserver joins the external `traefik-public`. Secrets come from the host's gitignored `.env`; the tracked `.templates/env.template` gains matching placeholders.

**Tech Stack:** Docker Compose, Traefik (cloudflare certresolver), Paperless-ngx 3.0.4, PostgreSQL 18, Valkey 9, Gotenberg 8.34, Apache Tika.

**Spec:** `docs/superpowers/specs/2026-07-29-paperless-ngx-design.md`

## Global Constraints

- Image tags are **pinned** for paperless, postgres, valkey and gotenberg. Do not use `latest` for these. Tika is the one exception (stateless, upstream tracks `latest`).
- **Do not** add `com.centurylinklabs.watchtower.enable=true` to any container in this stack. Watchtower runs `WATCHTOWER_LABEL_ENABLE=true`, so omitting the label is what keeps paperless off auto-update.
- **Do not** add authelia middleware — it breaks the mobile app and API tokens.
- **Do not** touch anything under `podman/`, and do not make Cloudflare DNS changes (a wildcard record already covers the hostname).
- Host paths use `${DOCKERDIR}` (`/mnt/appdata`, SSD) for state/db and `${DATADIR}` (`/mnt/main/data`, bulk) for documents. Never hardcode either.
- Real secrets go only in the host's `.env` (gitignored). `.templates/env.template` gets `<placeholder>` values and never real ones.
- Tasks 2 and 3 run **on docker-1**, not on the laptop: `manage.py` refuses to run against a non-`default` docker context because the bind mounts only exist on the host.

---

### Task 1: Compose stack and env template

**Files:**
- Create: `docker/services/paperless/docker-compose.yml`
- Modify: `.templates/env.template` (append a new block at end of file)
- Validation: `docker compose config` against a scratch env file

**Interfaces:**
- Consumes: `${DOCKERDIR}`, `${DATADIR}`, `${HOST_DOMAIN}`, `${TZ}`, `${PUID}`, `${PGID}` from `.env`; the external docker network `traefik-public`.
- Produces: the env var names Task 2 must populate on the host — `PAPERLESS_SECRET_KEY`, `PAPERLESS_DB_PASSWORD`, `PAPERLESS_ADMIN_USER`, `PAPERLESS_ADMIN_PASSWORD`. Produces the service name `paperless` used by `manage.py start|update|logs paperless`.

- [ ] **Step 1: Create the compose file**

Create `docker/services/paperless/docker-compose.yml` with exactly this content:

```yaml
# https://docs.paperless-ngx.com/
# Upstream reference: docker/compose/docker-compose.postgres-tika.yml
#
# Tags are pinned and there is deliberately no watchtower label here. Paperless
# runs irreversible schema migrations on upgrade - 3.0.2 existed only to repair
# one broken in 3.0.1 - so an unattended monday-morning pull is not something a
# document archive should be exposed to. Watchtower runs with
# WATCHTOWER_LABEL_ENABLE=true, so omitting the label is enough.
# To upgrade: read the release notes, bump the tag, "manage.py update paperless".

services:
  paperless:
    image: ghcr.io/paperless-ngx/paperless-ngx:3.0.4
    container_name: paperless
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
      broker:
        condition: service_healthy
      gotenberg:
        condition: service_started
      tika:
        condition: service_started
    volumes:
      # search index and classifier model: rebuildable but latency-sensitive
      - ${DOCKERDIR}/paperless/data:/usr/src/paperless/data
      # the documents themselves: irreplaceable and bulky
      - ${DATADIR}/paperless/media:/usr/src/paperless/media
      - ${DATADIR}/paperless/consume:/usr/src/paperless/consume
      - ${DATADIR}/paperless/export:/usr/src/paperless/export
    environment:
      - USERMAP_UID=${PUID:-1000}
      - USERMAP_GID=${PGID:-1000}
      - PAPERLESS_TIME_ZONE=${TZ}
      # required since 3.0 - the container refuses to start without it
      - PAPERLESS_SECRET_KEY=${PAPERLESS_SECRET_KEY}
      # sets ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS and CORS_ALLOWED_HOSTS at once
      - PAPERLESS_URL=https://paperless.${HOST_DOMAIN}
      # allauth rate-limits logins per client IP. Behind traefik every request
      # otherwise carries the same container IP, so a few failed logins from one
      # client would lock out everyone. All traffic here is cloudflare-proxied
      # (see cloudflare_ddns, PROXIED=true).
      - PAPERLESS_ALLAUTH_TRUSTED_CLIENT_IP_HEADER=CF-Connecting-IP
      # the image ships eng/deu/ita/spa/fra, so no extra langs to install
      - PAPERLESS_OCR_LANGUAGE=deu+eng
      - PAPERLESS_DBENGINE=postgresql
      - PAPERLESS_DBHOST=paperless_db
      - PAPERLESS_DBNAME=paperless
      - PAPERLESS_DBUSER=paperless
      - PAPERLESS_DBPASS=${PAPERLESS_DB_PASSWORD}
      - PAPERLESS_REDIS=redis://paperless_broker:6379
      - PAPERLESS_TIKA_ENABLED=1
      - PAPERLESS_TIKA_GOTENBERG_ENDPOINT=http://paperless_gotenberg:3000
      - PAPERLESS_TIKA_ENDPOINT=http://paperless_tika:9998
      # applied only on first start, while no such superuser exists
      - PAPERLESS_ADMIN_USER=${PAPERLESS_ADMIN_USER}
      - PAPERLESS_ADMIN_PASSWORD=${PAPERLESS_ADMIN_PASSWORD}
    labels:
      - traefik.enable=true
      - traefik.docker.network=traefik-public
      - traefik.http.routers.paperless.entrypoints=websecure
      - traefik.http.routers.paperless.tls.certresolver=cloudflare
      - traefik.http.routers.paperless.rule=Host(`paperless.${HOST_DOMAIN}`)
      - traefik.http.services.paperless.loadbalancer.server.scheme=http
      - traefik.http.services.paperless.loadbalancer.server.port=8000
    networks:
      - traefik-public
      - paperless_net
    # no healthcheck: the image ships its own against localhost:8000

  db:
    image: postgres:18
    container_name: paperless_db
    restart: unless-stopped
    volumes:
      # postgres:18 volumes /var/lib/postgresql, not /var/lib/postgresql/data
      # like the 17 image outline uses
      - ${DOCKERDIR}/paperless/db:/var/lib/postgresql
    environment:
      POSTGRES_DB: paperless
      POSTGRES_USER: paperless
      POSTGRES_PASSWORD: ${PAPERLESS_DB_PASSWORD}
    healthcheck:
      test: ["CMD", "pg_isready", "-d", "paperless", "-U", "paperless"]
      interval: 30s
      timeout: 20s
      retries: 3
    networks:
      - paperless_net

  broker:
    image: valkey/valkey:9-alpine
    container_name: paperless_broker
    restart: unless-stopped
    volumes:
      - ${DOCKERDIR}/paperless/redisdata:/data
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 10s
      timeout: 30s
      retries: 3
    networks:
      - paperless_net

  gotenberg:
    image: gotenberg/gotenberg:8.34
    container_name: paperless_gotenberg
    restart: unless-stopped
    # chromium is what converts .eml - no javascript and no remote content, so
    # an email cannot phone home with a tracking pixel during conversion
    command:
      - "gotenberg"
      - "--chromium-disable-javascript=true"
      - "--chromium-allow-list=file:///tmp/.*"
    networks:
      - paperless_net

  tika:
    image: apache/tika:latest
    container_name: paperless_tika
    restart: unless-stopped
    networks:
      - paperless_net

networks:
  traefik-public:
    external: true
  paperless_net: { }
```

- [ ] **Step 2: Append the env block to the template**

Append to the end of `.templates/env.template`:

```
################################################
# PAPERLESS-NGX
################################################
# Required since 3.0 - the container refuses to start if this is unset or left
# at "change-me".
#   python3 -c "import secrets; print(secrets.token_urlsafe(64))"
PAPERLESS_SECRET_KEY=<your_paperless_secret_key>
PAPERLESS_DB_PASSWORD=<your_paperless_db_password>  # openssl rand -base64 32
# Bootstrap superuser. Only created on first start, while no superuser exists.
PAPERLESS_ADMIN_USER=<your_paperless_admin_user>
PAPERLESS_ADMIN_PASSWORD=<your_paperless_admin_password>
```

- [ ] **Step 3: Build a scratch env file for validation**

The local `.env` has no paperless variables yet, and it must not be edited or copied for a validation run — it holds every secret in the homelab. Write a minimal file containing only the variables this compose file reads, with the same `DOCKERDIR`/`DATADIR`/`HOST_DOMAIN`/`TZ` values the host uses:

```bash
SCRATCH=/private/tmp/claude-501/-Users-jon-Downloads-homelab/d8d4e1f8-ebbf-44b3-af9c-f9da8b9730cf/scratchpad
cat > "$SCRATCH/pl-validate.env" <<'EOF'
TZ=Europe/Zurich
HOST_DOMAIN=mercantus.ch
DOCKERDIR=/mnt/appdata
DATADIR=/mnt/main/data
PAPERLESS_SECRET_KEY=validation-only
PAPERLESS_DB_PASSWORD=validation-only
PAPERLESS_ADMIN_USER=validation-only
PAPERLESS_ADMIN_PASSWORD=validation-only
EOF
```

`PUID`/`PGID` are deliberately absent — the compose file defaults them to `1000`, and this validates that the default works.

- [ ] **Step 4: Validate the compose file parses and interpolates**

Run:

```bash
SCRATCH=/private/tmp/claude-501/-Users-jon-Downloads-homelab/d8d4e1f8-ebbf-44b3-af9c-f9da8b9730cf/scratchpad
docker compose --env-file "$SCRATCH/pl-validate.env" \
  -f docker/services/paperless/docker-compose.yml config > "$SCRATCH/pl-rendered.yml"
echo "exit=$?"
```

Expected: `exit=0`, and **no** `WARN[...] The "SOMETHING" variable is not set` lines. A "variable is not set" warning means a typo in a variable name — fix it before continuing.

- [ ] **Step 5: Assert the rendered values are what the spec says**

Run:

```bash
SCRATCH=/private/tmp/claude-501/-Users-jon-Downloads-homelab/d8d4e1f8-ebbf-44b3-af9c-f9da8b9730cf/scratchpad
grep -c 'paperless.mercantus.ch' "$SCRATCH/pl-rendered.yml"   # expect 2 (router rule + PAPERLESS_URL)
grep -n '/mnt/appdata/paperless\|/mnt/main/data/paperless' "$SCRATCH/pl-rendered.yml"
grep -n 'watchtower' "$SCRATCH/pl-rendered.yml"                # expect NO output
grep -n 'image:' "$SCRATCH/pl-rendered.yml"
```

Expected:
- `2` occurrences of the hostname.
- Six bind-mount source paths: three under `/mnt/appdata/paperless` (`data`, `db`, `redisdata`), three under `/mnt/main/data/paperless` (`media`, `consume`, `export`).
- **Zero** watchtower lines — if any appear, a label leaked in and auto-update would be enabled.
- Images exactly: `ghcr.io/paperless-ngx/paperless-ngx:3.0.4`, `postgres:18`, `valkey/valkey:9-alpine`, `gotenberg/gotenberg:8.34`, `apache/tika:latest`.

- [ ] **Step 6: Confirm the env template stayed secret-free**

Run:

```bash
grep -A9 'PAPERLESS-NGX' .templates/env.template
```

Expected: every value is a `<placeholder>`; no generated key or password present.

- [ ] **Step 7: Commit**

```bash
git add docker/services/paperless/docker-compose.yml .templates/env.template
git commit -m "Add paperless-ngx 3.0 stack (pinned, no watchtower)"
```

---

### Task 2: Deploy on docker-1

**Runs on docker-1 (192.168.1.100), in the repo checkout there.** `manage.py` aborts if the docker context is not `default`, because `/mnt/appdata` and `/mnt/main` only exist on the host.

**Files:**
- Modify: `.env` on the host (gitignored, never committed)

**Interfaces:**
- Consumes: the four variable names produced by Task 1.
- Produces: a running stack; Task 3 verifies its behaviour.

- [ ] **Step 1: Pull the commit onto the host**

```bash
cd ~/homelab && git pull
```

Expected: `docker/services/paperless/docker-compose.yml` now exists on the host.

- [ ] **Step 2: Generate the secrets and append them to the host's `.env`**

```bash
cd ~/homelab
{
  echo ""
  echo "################################################"
  echo "# PAPERLESS-NGX"
  echo "################################################"
  echo "PAPERLESS_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
  echo "PAPERLESS_DB_PASSWORD=$(openssl rand -base64 32 | tr -d '\n')"
  echo "PAPERLESS_ADMIN_USER=jon"
  echo "PAPERLESS_ADMIN_PASSWORD=CHOOSE_A_PASSWORD_HERE"
} >> .env
```

Then edit `.env`: replace `CHOOSE_A_PASSWORD_HERE` with a real password, and change `PAPERLESS_ADMIN_USER=jon` if you want a different login name. Confirm with:

```bash
grep -c '^PAPERLESS_' .env    # expect 4
git status --porcelain .env   # expect NO output - .env is gitignored
```

- [ ] **Step 3: Confirm manage.py discovers the service**

```bash
python3 manage.py list | grep -i paperless
```

Expected: `paperless` appears under the services list. If it does not, the compose file is not at `docker/services/paperless/docker-compose.yml`.

- [ ] **Step 4: Start the stack**

```bash
python3 manage.py start paperless
```

Expected: five containers created. First start pulls ~2 GB and runs migrations, so give it a few minutes.

- [ ] **Step 5: Verify all five containers are up and paperless is healthy**

```bash
docker ps --filter name=paperless --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
```

Expected: `paperless`, `paperless_db`, `paperless_broker`, `paperless_gotenberg`, `paperless_tika` all `Up`, and `paperless` showing `(healthy)`. If `paperless` is restarting, check `docker logs paperless` for `PAPERLESS_SECRET_KEY` — an unset key is the most likely cause on 3.0.

- [ ] **Step 6: Verify no permission warnings from the init**

```bash
docker logs paperless 2>&1 | grep -i 'init-folders\|init-user\|WARNING'
```

Expected: `[init-user]` mapping lines and `[init-folders] Running with root privileges` — and **no** `Permission issue` or `Could not create` warnings. Those would mean the bind-mount dirs were not chowned to UID 1000.

- [ ] **Step 7: Verify the route serves over TLS**

```bash
curl -sSI https://paperless.mercantus.ch | head -3
```

Expected: `HTTP/2 302` or `200` with no TLS error. A certificate error means the `cloudflare` certresolver has not issued yet — wait a minute and retry.

- [ ] **Step 8: Log in**

In a browser, open `https://paperless.mercantus.ch` and log in with `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD`.

Expected: the paperless dashboard loads, empty.

---

### Task 3: Functional acceptance

**Runs on docker-1.** Proves OCR, the tika/gotenberg path, and search actually work — not just that containers are up.

- [ ] **Step 1: Drop a PDF into the consume folder**

```bash
cp /path/to/some/scanned.pdf /mnt/main/data/paperless/consume/
```

Use a German-language PDF if you have one — that is what `deu+eng` is there for.

- [ ] **Step 2: Watch it get consumed**

```bash
docker logs -f paperless 2>&1 | grep -i 'consum\|ocr'
```

Expected: lines showing the file detected, OCR'd, and stored. Ctrl-C when it reports the document was added. The file disappears from `consume/`.

- [ ] **Step 3: Confirm it is searchable**

In the web UI, search for a word that appears in the PDF's body text (not its filename).

Expected: the document is returned. This is the Tantivy index working — a hit here means the 3.0 search backend indexed the OCR output.

- [ ] **Step 4: Drop a .docx to exercise tika + gotenberg**

```bash
cp /path/to/some/document.docx /mnt/main/data/paperless/consume/
docker logs -f paperless 2>&1 | grep -i 'consum\|tika\|gotenberg'
```

Expected: consumed and converted to an archived PDF. An error mentioning a connection to `paperless_tika:9998` or `paperless_gotenberg:3000` means the endpoint env vars are wrong.

- [ ] **Step 5: Confirm the documents landed on the bulk pool**

```bash
ls -la /mnt/main/data/paperless/media/documents/originals/
du -sh /mnt/main/data/paperless/media /mnt/appdata/paperless
```

Expected: the originals are under `/mnt/main/data` (bulk), and `/mnt/appdata/paperless` holds only the index, db and queue. If documents ended up on the appdata pool, a volume mapping is swapped.

- [ ] **Step 6: Record the result**

No code change. Report which of steps 1–5 passed, with the actual command output — do not claim success for a step whose output was not seen.

---

## Rollback

If the stack misbehaves and needs removing:

```bash
cd ~/homelab && python3 manage.py stop paperless
sudo rm -rf /mnt/appdata/paperless /mnt/main/data/paperless   # destroys all documents
```

Removing the four `PAPERLESS_*` lines from `.env` and reverting the Task 1 commit returns the repo to its prior state.
