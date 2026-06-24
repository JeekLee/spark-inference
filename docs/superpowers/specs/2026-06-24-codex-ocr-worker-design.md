# Codex Prompt/Image Worker Design

## Goal

Add gateway-protected Codex prompt/image endpoints that use existing Codex
subscription access instead of OpenAI Platform vision API billing. The endpoints
are intended as a pragmatic fallback for low-volume OCR, screenshot analysis,
visual extraction, and lightweight text-only Codex tasks when local Qwen VL
inference is too slow.

## Non-Goals

- Do not make Codex a generic OpenAI-compatible inference backend.
- Do not change existing `/v1/chat/completions`, `/v1/embeddings`, or `/v1/rerank`
  routing.
- Do not expose Codex app-server directly over the network.
- Do not implement high-throughput batch or long-running agent workflows in the
  first version.

## API

Add:

- `POST /v1/codex`: non-streaming prompt/image run.
- `POST /v1/codex/stream`: SSE wrapper around Codex JSONL events.
- `POST /v1/ocr`: compatibility alias with an OCR-specific default prompt.

The route uses the existing `Authorization: Bearer <GATEWAY_MASTER_KEY>` check.
The request accepts `multipart/form-data` with:

- `image`: optional uploaded PNG/JPEG/WebP image for `/v1/codex`; required for `/v1/ocr`.
- `prompt`: optional instruction override.
- `timeout_seconds`: optional bounded timeout.

The response is JSON:

```json
{
  "text": "...",
  "raw": "...",
  "engine": "codex-cli"
}
```

`text` is the best extracted text. `raw` is the final Codex response so callers can
inspect formatting drift.

## Architecture

The gateway stores any uploaded image in a private temporary directory, then runs
Codex CLI non-interactively:

```bash
codex --ask-for-approval never exec --sandbox read-only "..." --image /tmp/.../image.png
```

For streaming, the gateway adds `--json` and converts each Codex JSONL stdout
line into an SSE `codex` event, followed by a `done` event. The prompt tells
Codex to avoid shell/file edits, network browsing, and unrelated work. The
gateway captures stdout, applies a timeout, deletes temporary files, and returns
the final result or event stream.

The first implementation uses the CLI subprocess rather than the SDK because the
CLI has a documented image attachment flag. The SDK/app-server path can replace
this later if its image input behavior is stable enough for the gateway.

## Configuration

Add environment variables:

- `GATEWAY_CODEX_ENABLED`: default `false`.
- `GATEWAY_CODEX_BIN`: default `codex`.
- `GATEWAY_CODEX_TIMEOUT_SECONDS`: default `120`.
- `GATEWAY_CODEX_MAX_IMAGE_BYTES`: default `10485760`.

Codex authentication is provided by the container's Codex auth cache or by
environment supplied by the operator. The gateway must not log tokens or uploaded
image contents.

## Error Handling

- Disabled endpoints return `404` so they do not appear available by accident.
- Missing image on `/v1/ocr` returns `422` through FastAPI validation.
- Missing prompt and missing image on `/v1/codex` returns `400`.
- Unsupported content type or oversized upload returns `400` or `413`.
- Codex timeout returns `504`.
- Codex nonzero exit returns `502` with a short sanitized error message.
  Streaming routes send an SSE `error` event after streaming has started.

## Security

The endpoint is protected by the existing gateway bearer token. Uploaded images
are written to a per-request temporary directory and removed after the subprocess
finishes. Codex runs with `read-only` sandbox and `never` approval mode, and the
prompt explicitly forbids code changes, network browsing, or unrelated work.

Because Codex account credentials are sensitive, mounting `~/.codex/auth.json`
into the gateway container should be treated as a privileged deployment choice.
This endpoint should stay disabled unless that operational risk is accepted.

## Tests

Add focused tests around:

- auth dependency still protects `/v1/codex`, `/v1/codex/stream`, and `/v1/ocr`;
- disabled endpoint behavior;
- image validation and max-size handling;
- subprocess command construction without invoking real Codex;
- timeout and subprocess failure mapping.

Use monkeypatching for the Codex subprocess boundary and JSONL stream boundary
so tests do not consume Codex quota.
