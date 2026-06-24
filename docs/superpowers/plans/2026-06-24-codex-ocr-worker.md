# Codex Prompt/Image Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bearer-protected `/v1/codex` and `/v1/codex/stream` endpoints that invoke Codex CLI for prompt/image tasks without using OpenAI Platform vision API billing.

**Architecture:** Keep the existing FastAPI gateway as the only exposed server. Add a small Codex boundary inside `deployment/networks/gateway/app/main.py` that validates optional image uploads, writes temporary image files, invokes `codex exec` or `codex exec --json`, maps failures to HTTP/SSE errors, and removes temporary files. Tests monkeypatch the subprocess and JSONL stream boundaries so no real Codex quota is consumed.

**Tech Stack:** FastAPI, Python 3.12, `asyncio.create_subprocess_exec`, `pytest`, FastAPI `TestClient`.

---

## File Structure

- Modify `deployment/networks/gateway/app/main.py`: add Codex configuration, upload validation, Codex CLI subprocess helper, `POST /v1/codex`, `POST /v1/codex/stream`, and `POST /v1/ocr` compatibility alias.
- Modify `deployment/networks/gateway/requirements.txt`: add test/runtime support only if needed.
- Modify `envs/networks/gateway/.env.example`: document OCR feature flag and limits.
- Modify `deployment/networks/gateway/API.md`: document `/v1/codex`, `/v1/codex/stream`, and `/v1/ocr` alias.
- Create `tests/gateway/test_codex_ocr.py`: focused tests for disabled behavior, auth, validation, success, streaming, timeout, and subprocess failure.

## Task 1: Add Failing Codex Route Tests

**Files:**
- Create: `tests/gateway/test_codex_ocr.py`
- Modify: none

- [ ] **Step 1: Write failing tests**

Create tests that import the gateway with temp env vars, monkeypatch Codex execution, and exercise `/v1/codex`, `/v1/codex/stream`, and `/v1/ocr`.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest tests/gateway/test_codex_ocr.py -q`
Expected: FAIL before implementation because `/v1/codex` and `/v1/codex/stream` do not exist.

## Task 2: Implement Minimal Codex Endpoints

**Files:**
- Modify: `deployment/networks/gateway/app/main.py`

- [ ] **Step 1: Add OCR config and helper functions**

Add env parsing, accepted MIME types, image upload validation, `_run_codex_once`, and `_stream_codex_jsonl`.

- [ ] **Step 2: Add route**

Add `POST /v1/codex` and `POST /v1/codex/stream` with `Depends(require_bearer)`, optional `UploadFile`, optional `prompt`, optional `timeout_seconds`, and disabled behavior. Keep `POST /v1/ocr` as an image-required alias.

- [ ] **Step 3: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/gateway/test_codex_ocr.py -q`
Expected: PASS.

## Task 3: Document and Verify

**Files:**
- Modify: `envs/networks/gateway/.env.example`
- Modify: `deployment/networks/gateway/API.md`

- [ ] **Step 1: Document env vars**

Add disabled-by-default Codex settings and explain Codex auth cache requirement.

- [ ] **Step 2: Document API**

Add request/response examples and operational caveats.

- [ ] **Step 3: Run final verification**

Run: `.venv/bin/python -m pytest tests/gateway/test_codex_ocr.py -q`
Run: `python3 -m compileall deployment/networks/gateway/app`
Expected: both PASS.

## Self-Review

- Spec coverage: endpoint, auth, CLI image path, config, error mapping, security, and tests are covered.
- Placeholder scan: no placeholder steps remain.
- Type consistency: route uses FastAPI `UploadFile`; subprocess helper returns a string; HTTP response contains `text`, `raw`, and `engine`.
