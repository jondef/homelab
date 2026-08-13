# Paperless-ngx AI Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Paperless-ngx 3.0's native AI features (suggestions, document chat, similar-document retrieval) backed by a local Ollama sidecar, and add Spanish to OCR.

**Architecture:** One file changes: `docker/services/paperless/docker-compose.yml` gains an `ollama` service on the private `paperless_net` (never on `traefik-public`), and the `paperless` service gains seven `PAPERLESS_AI_*` env vars pointing at it plus `spa` in the OCR languages. Nothing is deployed from this machine — the stack is committed-but-undeployed; deploy steps are user-run on docker-1.

**Tech Stack:** docker compose, ollama 0.32.9, gemma4:e4b (generation), embeddinggemma (embeddings), paperless-ngx 3.0.4.

**Spec:** `docs/superpowers/specs/2026-08-12-paperless-ai-design.md`

## Global Constraints

- All image tags pinned; NO watchtower label anywhere in this stack (watchtower runs with `WATCHTOWER_LABEL_ENABLE=true`, so absence = no auto-update).
- Ollama joins `paperless_net` ONLY — it must not appear on `traefik-public` and must have no traefik labels and no published ports.
- Resource caps on ollama exactly: `cpus: 12`, `mem_limit: 12g` (16-vCPU/32 GB VM shared with ~50 containers).
- No `depends_on` from `paperless` to `ollama` — paperless runs fine without the AI backend.
- The real `.env` must never be edited or copied for validation; use a minimal scratch env file.
- Comments in the compose file explain *why*, matching the file's existing style.

---

### Task 1: Ollama sidecar + AI env vars in the paperless compose file

**Files:**
- Modify: `docker/services/paperless/docker-compose.yml` (env block ~lines 53-66, new service after `tika` ~line 132)

**Interfaces:**
- Consumes: existing `paperless_net` network and `${DOCKERDIR}` env var, both already in the file.
- Produces: container `paperless_ollama` serving the Ollama API at `http://paperless_ollama:11434` on `paperless_net`; env contract `PAPERLESS_AI_LLM_MODEL=gemma4:e4b` / `PAPERLESS_AI_LLM_EMBEDDING_MODEL=embeddinggemma` that the deploy-day `ollama pull` commands must match.

- [ ] **Step 1: Change the OCR language line**

In `docker/services/paperless/docker-compose.yml`, the existing lines

```yaml
      # the image ships eng/deu/ita/spa/fra, so no extra langs to install
      - PAPERLESS_OCR_LANGUAGE=deu+eng
```

become

```yaml
      # the image ships eng/deu/ita/spa/fra, so no extra langs to install
      - PAPERLESS_OCR_LANGUAGE=deu+eng+spa
```

- [ ] **Step 2: Add the AI env vars to the `paperless` service**

Insert directly after the `- PAPERLESS_ADMIN_PASSWORD=${PAPERLESS_ADMIN_PASSWORD}` line (end of the environment block):

```yaml
      # AI features (new in 3.0, opt-in): LLM suggestions, document chat and
      # similar-document retrieval, all against the local ollama sidecar -
      # no document content leaves the network. Both models must be pulled
      # once on deploy (see the ollama service below). Answers are fallible;
      # the documents stay authoritative.
      - PAPERLESS_AI_ENABLED=true
      - PAPERLESS_AI_LLM_BACKEND=ollama
      - PAPERLESS_AI_LLM_MODEL=gemma4:e4b
      - PAPERLESS_AI_LLM_ENDPOINT=http://paperless_ollama:11434
      # embeddings build the RAG/similarity index (rebuilt nightly at 02:10
      # by default); changing this model requires "document_llmindex rebuild"
      - PAPERLESS_AI_LLM_EMBEDDING_BACKEND=ollama
      - PAPERLESS_AI_LLM_EMBEDDING_MODEL=embeddinggemma
      # CPU inference: RAG-backed suggestions can exceed the 120s default
      - PAPERLESS_AI_LLM_REQUEST_TIMEOUT=300
```

Note: no `PAPERLESS_AI_LLM_EMBEDDING_ENDPOINT` (defaults to `PAPERLESS_AI_LLM_ENDPOINT`), no `PAPERLESS_LLM_INDEX_TASK_CRON` (default 02:10 nightly is fine).

- [ ] **Step 3: Add the `ollama` service**

Insert after the `tika` service block (before the top-level `networks:` key):

```yaml
  ollama:
    image: ollama/ollama:0.32.9
    container_name: paperless_ollama
    restart: unless-stopped
    # CPU-only inference (docker-1 has no GPU). The caps keep a long chat
    # answer from starving the other containers on this 16-core/32GB VM;
    # ollama unloads idle models after 5 min, so the RAM cost is transient.
    # No depends_on from paperless: it runs fine without the AI backend.
    # Models are pulled once, manually, on deploy:
    #   docker exec paperless_ollama ollama pull gemma4:e4b
    #   docker exec paperless_ollama ollama pull embeddinggemma
    cpus: 12
    mem_limit: 12g
    volumes:
      # pulled models: rebuildable (re-pull), but multi-GB - fast pool
      - ${DOCKERDIR}/paperless/ollama:/root/.ollama
    # paperless_net only - the API is unauthenticated, so it must stay
    # unreachable from outside the stack (no traefik-public, no ports)
    networks:
      - paperless_net
```

- [ ] **Step 4: Build the minimal scratch env file for validation**

The real `.env` holds every secret in the homelab — never edit or copy it for a validation run. Write a minimal file with only the variables this compose file reads:

```bash
SCRATCH=/private/tmp/claude-501/-Users-jon-Downloads-homelab/9efa9558-d545-4720-a320-22240f12b2c0/scratchpad
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

- [ ] **Step 5: Validate the compose file parses and interpolates**

```bash
SCRATCH=/private/tmp/claude-501/-Users-jon-Downloads-homelab/9efa9558-d545-4720-a320-22240f12b2c0/scratchpad
docker compose --env-file "$SCRATCH/pl-validate.env" \
  -f docker/services/paperless/docker-compose.yml config > "$SCRATCH/pl-rendered.yml"
echo "exit=$?"
```

Expected: `exit=0` and **no** `WARN[...] The "SOMETHING" variable is not set` lines (such a warning means a typo in a variable name — fix before continuing).

- [ ] **Step 6: Assert the rendered values match the spec**

```bash
SCRATCH=/private/tmp/claude-501/-Users-jon-Downloads-homelab/9efa9558-d545-4720-a320-22240f12b2c0/scratchpad
grep -n 'image:' "$SCRATCH/pl-rendered.yml"
grep -n 'watchtower' "$SCRATCH/pl-rendered.yml"                  # expect NO output
grep -n 'PAPERLESS_AI\|PAPERLESS_OCR_LANGUAGE' "$SCRATCH/pl-rendered.yml"
grep -n '/mnt/appdata/paperless/ollama' "$SCRATCH/pl-rendered.yml"
# ollama must NOT be on traefik-public: in the rendered ollama service,
# networks must list only paperless_net
sed -n '/^  ollama:/,/^  [a-z]/p' "$SCRATCH/pl-rendered.yml" | grep -A3 'networks:'
```

Expected:
- Images exactly: `ghcr.io/paperless-ngx/paperless-ngx:3.0.4`, `postgres:18`, `valkey/valkey:9-alpine`, `gotenberg/gotenberg:8.34`, `apache/tika:latest`, `ollama/ollama:0.32.9`.
- **Zero** watchtower lines.
- All seven `PAPERLESS_AI_*` vars rendered with the values from Step 2; `PAPERLESS_OCR_LANGUAGE: deu+eng+spa`.
- Bind mount `/mnt/appdata/paperless/ollama` → `/root/.ollama` present.
- The ollama service's networks list contains `paperless_net` and NOT `traefik-public`; no `labels:` and no `ports:` on the ollama service.

- [ ] **Step 7: Commit**

```bash
git add docker/services/paperless/docker-compose.yml
git commit -m "Enable paperless AI features with local ollama sidecar

gemma4:e4b for suggestions/chat, embeddinggemma for the RAG index,
CPU-capped on paperless_net only. Adds spa to OCR languages."
```

---

## Deploy (user-run on docker-1, not part of this plan's execution)

The stack is still undeployed; these ride along with the initial deployment steps from `docs/superpowers/plans/2026-07-29-paperless-ngx.md`:

```bash
python3 manage.py update paperless
docker exec paperless_ollama ollama pull gemma4:e4b
docker exec paperless_ollama ollama pull embeddinggemma
```

After documents exist, build the embedding index immediately (instead of waiting for the 02:10 cron):

```bash
docker exec paperless document_llmindex rebuild
```

Smoke test: open a document → request AI suggestions; ask one chat question against a ~20-doc test batch before any bulk import.
