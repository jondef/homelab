# Paperless-ngx AI features — Design

**Date:** 2026-08-12
**Status:** Approved

## Goal

Enable Paperless-ngx 3.0's native, opt-in AI features (LLM suggestions,
document chat, similar-document retrieval) on the existing
`docker/services/paperless` stack, backed by a local Ollama sidecar so no
document content leaves the network. Also widen OCR to cover the Spanish
documents in the archive.

This is the follow-up the 2026-07-29 paperless design explicitly deferred
("no active ollama service to point them at").

## Out of scope

- Importing the Nextcloud admin folder. Separate follow-up; the user wants
  to design the import + tagging workflow properly on its own.
- `PAPERLESS_CONSUMER_SUBDIRS_AS_TAGS`. Belongs to that import design, and
  the preferred tagging path is AI suggestions + the auto-matching
  classifier, not folder names.
- Reviving open-webui / `chat.mercantus.ch` from `docker/_archive/ollama`.
  Paperless's own chat UI is the interface here.
- GPU. docker-1 has none; this is CPU inference, sized accordingly.
- Sharing Ollama with other services (n8n). If that ever happens, promote
  the sidecar to its own stack then.

## Model choice

CPU-only constraint: docker-1 is a 16-vCPU / 32 GB VM already running ~50
containers. Current (Aug 2026) community consensus for CPU-only boxes is a
4B-class model at Q4 — smaller models are reported flaky at structured
output (tag/correspondent suggestions), larger ones are chat-unusable
without a GPU.

| Role | Model | Why |
|---|---|---|
| Generation | `gemma4:e4b` | Consensus CPU pick alongside qwen3.5:4b; chosen over qwen because Gemma is guaranteed non-thinking — a thinking model on CPU can burn the whole request timeout "reasoning". Multilingual (deu/eng/spa), ~5 GB at Q4, ~10 tok/s on these cores. |
| Embedding | `embeddinggemma` | Paperless's documented Ollama default. 300M params, multilingual, fast on CPU. Builds the RAG/similarity index. |

Fallbacks if suggestion quality disappoints: `qwen3.5:4b`, then
`gemma4:12b` (2× latency, ~8 GB). Each is a one-line env change plus an
`ollama pull`; changing the *embedding* model additionally requires an LLM
index rebuild.

## Layout

No new directories. Two kinds of change to
`docker/services/paperless/docker-compose.yml`:

### New `ollama` service (sidecar)

| Aspect | Value | Why |
|---|---|---|
| Image | `ollama/ollama:0.32.9` | Pinned like the rest of the stack; no watchtower label, same policy |
| Container name | `paperless_ollama` | Matches stack naming (`paperless_db`, …) |
| Networks | `paperless_net` only | Never on `traefik-public`; unreachable from outside the stack |
| Model storage | `${DOCKERDIR}/paperless/ollama:/root/.ollama` | Rebuildable (re-pull), latency-sensitive — same reasoning as the data dir |
| Limits | `cpus: 12`, `mem_limit: 12g` | A long chat answer must not starve the other containers on the 16-core/32 GB VM |

Ollama unloads idle models after 5 minutes (default keep-alive), so the
~6 GB model RAM cost is transient; first request after idle pays a
~10–30 s load-from-disk penalty.

`depends_on` for ollama is deliberately omitted on the paperless service:
paperless starts fine without the AI backend and only needs it when an AI
request is made.

### Paperless environment additions

```
PAPERLESS_AI_ENABLED=true
PAPERLESS_AI_LLM_BACKEND=ollama
PAPERLESS_AI_LLM_MODEL=gemma4:e4b
PAPERLESS_AI_LLM_ENDPOINT=http://paperless_ollama:11434
PAPERLESS_AI_LLM_EMBEDDING_BACKEND=ollama
PAPERLESS_AI_LLM_EMBEDDING_MODEL=embeddinggemma
PAPERLESS_AI_LLM_REQUEST_TIMEOUT=300
```

- Timeout 300: upstream wiki advice for slow local inference; RAG-backed
  suggestions retrieve context from similar documents and can exceed the
  120 s default on CPU.
- Embedding endpoint defaults to `PAPERLESS_AI_LLM_ENDPOINT` — not set
  separately.
- `PAPERLESS_LLM_INDEX_TASK_CRON` left at its default (02:10 nightly
  embedding refresh).
- `PAPERLESS_AI_LLM_OUTPUT_LANGUAGE` left unset (follows UI language).

And one change: `PAPERLESS_OCR_LANGUAGE=deu+eng` → `deu+eng+spa`. The
image ships spa already; no install step. OCR remains default `skip` mode:
existing text layers are kept, only pages without text get recognized.

## Deploy (user-run on docker-1)

The stack is committed but not yet deployed (per 2026-07-29 design), so
this rides along with the initial deployment. Incremental steps:

```
python3 manage.py update paperless
docker exec paperless_ollama ollama pull gemma4:e4b
docker exec paperless_ollama ollama pull embeddinggemma
```

Models must be pulled once before the first AI request; paperless does not
pull them itself. After documents exist, the embedding index builds on the
nightly cron, or immediately via
`docker exec paperless document_llmindex rebuild`.

## Error handling

- Ollama down / model missing: paperless works normally; AI suggestions
  and chat fail with an error in the UI, nothing else degrades.
- AI answers are fallible (features are new upstream) — treat chat output
  as a retrieval aid, not a source of truth. The documents themselves are
  authoritative.

## Testing

- `manage.py` compose validation (same minimal-env check used by
  `tests/test_manage.py`) still passes with the edited file.
- Post-deploy smoke test: pull models, open a document, request AI
  suggestions; ask one chat question against a test batch of ~20 docs
  before bulk import.
