"""spark-gateway — single-port FastAPI gateway for spark-inference.

Replaces LiteLLM. 두 종류 백엔드 통합:

1. **inference** (vLLM / TEI 등 OpenAI-compatible) — 모델별 `/v1/*` 라우팅.
   클라이언트가 보낸 `model` 필드를 보고 등록된 백엔드 base URL 로 forward.
   `/v1/models` 는 등록된 모델 목록을 자체 응답.

2. **audio** (FastAPI multipart/binary) — path 기반 라우팅. 요청 body 를
   원형 그대로 (multipart boundary 보존) target URL 로 forward 하고 응답을
   chunked stream 으로 그대로 클라이언트에 전달.

Auth: 모든 비-health/비-metrics 엔드포인트는 `Authorization: Bearer
<GATEWAY_MASTER_KEY>` 필수. compose `:?` 가드 + Python `RuntimeError` 양쪽으로
키 미설정 시 boot 거부.

라우팅 테이블은 startup 시 한 번 `routes.yaml` 에서 읽음. 라우트 변경은
컨테이너 재시작 단위 — 매니페스트 = gateway 라우팅, drift 원천 차단.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import yaml
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.background import BackgroundTask

logging.basicConfig(level=os.environ.get("GATEWAY_LOG_LEVEL", "INFO"))
log = logging.getLogger("spark-gateway")

_MASTER_KEY = os.environ.get("GATEWAY_MASTER_KEY", "")
if not _MASTER_KEY:
    raise RuntimeError(
        "GATEWAY_MASTER_KEY env var must be set — "
        "see envs/networks/gateway/.env.example"
    )

_ROUTES_PATH = Path(os.environ.get("GATEWAY_ROUTES_PATH", "/app/routes.yaml"))
if not _ROUTES_PATH.exists():
    raise RuntimeError(f"routes file not found: {_ROUTES_PATH}")


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


_CODEX_ENABLED = _env_bool(
    "GATEWAY_CODEX_ENABLED",
    default=_env_bool("GATEWAY_CODEX_OCR_ENABLED", default=False),
)
_CODEX_OCR_ENABLED = _CODEX_ENABLED
_CODEX_BIN = os.environ.get("GATEWAY_CODEX_BIN", "codex")
_CODEX_TIMEOUT_SECONDS = float(
    os.environ.get("GATEWAY_CODEX_TIMEOUT_SECONDS", os.environ.get("GATEWAY_CODEX_OCR_TIMEOUT_SECONDS", "120"))
)
_CODEX_OCR_TIMEOUT_SECONDS = _CODEX_TIMEOUT_SECONDS
_CODEX_MAX_IMAGE_BYTES = int(
    os.environ.get("GATEWAY_CODEX_MAX_IMAGE_BYTES", os.environ.get("GATEWAY_CODEX_OCR_MAX_BYTES", "10485760"))
)
_CODEX_OCR_MAX_BYTES = _CODEX_MAX_IMAGE_BYTES
_CODEX_IMAGE_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_CODEX_DEFAULT_PROMPT = (
    "Analyze the attached image or answer the prompt. Return only the useful "
    "result for the caller. Do not edit files, run commands, browse the network, "
    "or do any unrelated work."
)
_CODEX_OCR_DEFAULT_PROMPT = (
    "Extract all visible text from the attached image. Return only the extracted "
    "text. Preserve line breaks when useful. If no text is visible, return an "
    "empty string. Do not edit files, run commands, browse the network, or do "
    "any unrelated work."
)


with _ROUTES_PATH.open() as fh:
    _cfg: dict[str, Any] = yaml.safe_load(fh) or {}

_inference_models: dict[str, str] = {}   # model_name → backend base URL (e.g. http://qwen3-8b:8000)
_audio_routes: dict[str, str] = {}       # path → target URL (full, e.g. http://madmom-chord:8000/chords)

for entry in _cfg.get("backends", []) or []:
    kind = entry.get("kind")
    if kind == "inference":
        model = entry["model"]
        url = entry["url"].rstrip("/")
        _inference_models[model] = url
    elif kind == "audio":
        path = entry["path"]
        target = entry["target"]
        _audio_routes[path] = target
    else:
        log.warning("unknown backend kind: %r", kind)

log.info(
    "spark-gateway: %d inference model(s), %d audio route(s)",
    len(_inference_models), len(_audio_routes),
)
for m, u in _inference_models.items():
    log.info("  inference: %-20s → %s", m, u)
for p, t in _audio_routes.items():
    log.info("  audio:     %-20s → %s", p, t)


# ── HTTP client + proxy helper ─────────────────────────────────────────────
# 긴 timeout — htdemucs/qwen 같은 느린 추론 응답을 기다림.
_client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=5.0, read=600.0, write=120.0, pool=30.0),
    limits=httpx.Limits(max_keepalive_connections=64, max_connections=128),
)


def _filter_request_headers(src: dict[str, str]) -> dict[str, str]:
    """원본 request 헤더에서 hop-by-hop / 게이트웨이 자체용 헤더 제거.

    `host` 는 httpx 가 target URL 기준으로 다시 박음. `authorization` 은
    백엔드가 인증 안 하므로 떼는 게 깨끗 (백엔드 컨테이너는 internal docker
    network 만 보임). `content-length` 와 `transfer-encoding` 은 httpx 가
    `content=body` 로 다시 계산하므로 떨궈야 한다 — 안 떨구면 클라이언트가
    chunked 로 보낸 경우 원본의 `Transfer-Encoding: chunked` 와 httpx 가
    새로 박은 `Content-Length` 가 동시에 forward 되어 RFC 7230 §3.3.3 위반
    (request smuggling 의심) 이 되고 uvicorn/h11 백엔드가 "Invalid HTTP
    request received." 로 400 거부. (예: Spring AI 1.0 의 RestClient + HC5
    streaming entity 가 정확히 이 케이스.)
    """
    drop = {"host", "authorization", "content-length", "transfer-encoding", "connection"}
    return {k: v for k, v in src.items() if k.lower() not in drop}


def _filter_response_headers(src: dict[str, str]) -> dict[str, str]:
    """백엔드 응답 헤더 중 starlette 가 다시 계산하는 것들 제거."""
    drop = {"content-encoding", "transfer-encoding", "content-length", "connection"}
    return {k: v for k, v in src.items() if k.lower() not in drop}


async def _proxy(
    request: Request,
    target_url: str,
    *,
    body: bytes | None = None,
) -> StreamingResponse:
    """target_url 로 method/headers/query/body 그대로 forward 후 응답 stream.

    `body` 가 명시적으로 주어지면 그것을 사용 (chat completions 처럼 라우팅
    위해 미리 read 한 경우). 없으면 request body 를 직접 read.
    """
    if body is None:
        body = await request.body()

    fwd_headers = _filter_request_headers(dict(request.headers))

    httpx_req = _client.build_request(
        method=request.method,
        url=target_url,
        params=dict(request.query_params),
        headers=fwd_headers,
        content=body,
    )
    try:
        resp = await _client.send(httpx_req, stream=True)
    except httpx.ConnectError as exc:
        log.warning("backend unreachable: %s (%s)", target_url, exc)
        raise HTTPException(status_code=502, detail=f"backend unreachable: {exc}") from exc
    except httpx.RequestError as exc:
        log.warning("backend request error: %s (%s)", target_url, exc)
        raise HTTPException(status_code=502, detail=f"backend error: {exc}") from exc

    return StreamingResponse(
        resp.aiter_raw(),
        status_code=resp.status_code,
        headers=_filter_response_headers(dict(resp.headers)),
        media_type=resp.headers.get("content-type"),
        background=BackgroundTask(resp.aclose),
    )


# ── Auth ───────────────────────────────────────────────────────────────────
async def require_bearer(authorization: str = Header(default="")) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    if authorization[len("Bearer "):] != _MASTER_KEY:
        raise HTTPException(status_code=401, detail="invalid master key")


# ── Codex prompt/image helper ──────────────────────────────────────────────
def _build_codex_cmd(
    image_path: Path | None,
    prompt: str,
    *,
    json_mode: bool = False,
) -> list[str]:
    cmd = [
        _CODEX_BIN,
        "--ask-for-approval",
        "never",
        "exec",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--color",
        "never",
    ]
    if json_mode:
        cmd.append("--json")
    cmd.append(prompt)
    if image_path is not None:
        # Codex CLI defines --image as variadic, so positional prompt must
        # come before it or the prompt is parsed as another image path.
        cmd.extend(["--image", str(image_path)])
    return cmd


async def _run_codex_once(image_path: Path | None, prompt: str, timeout_seconds: float) -> str:
    cmd = _build_codex_cmd(image_path, prompt)
    cwd = str(image_path.parent if image_path is not None else Path(tempfile.gettempdir()))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"codex binary not found: {_CODEX_BIN}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise TimeoutError("codex OCR timed out") from exc

    out_text = stdout.decode("utf-8", errors="replace").strip()
    err_text = stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        detail = (err_text or out_text or "no output")[:500]
        raise RuntimeError(f"codex failed with exit code {proc.returncode}: {detail}")
    return out_text


async def _stream_codex_jsonl(
    image_path: Path | None,
    prompt: str,
    timeout_seconds: float,
) -> AsyncIterator[str]:
    cmd = _build_codex_cmd(image_path, prompt, json_mode=True)
    cwd = str(image_path.parent if image_path is not None else Path(tempfile.gettempdir()))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"codex binary not found: {_CODEX_BIN}") from exc

    assert proc.stdout is not None
    assert proc.stderr is not None
    stderr = b""
    try:
        async with asyncio.timeout(timeout_seconds):
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    yield text
            stderr = await proc.stderr.read()
            returncode = await proc.wait()
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise TimeoutError("codex stream timed out") from exc

    if returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()[:500] or "no output"
        raise RuntimeError(f"codex failed with exit code {returncode}: {detail}")


async def _run_codex_ocr(image_path: Path, prompt: str, timeout_seconds: float) -> str:
    return await _run_codex_once(image_path, prompt, timeout_seconds)


async def _read_codex_image(image: UploadFile) -> tuple[bytes, str]:
    content_type = image.content_type or "application/octet-stream"
    suffix = _CODEX_IMAGE_CONTENT_TYPES.get(content_type)
    if suffix is None:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported image content type: {content_type}",
        )

    body = await image.read()
    if len(body) > _CODEX_MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"image exceeds max size of {_CODEX_MAX_IMAGE_BYTES} bytes",
        )
    return body, suffix


async def _read_optional_codex_image(image: UploadFile | None) -> tuple[bytes | None, str | None]:
    if image is None:
        return None, None
    return await _read_codex_image(image)


def _resolve_codex_prompt(prompt: str | None, *, has_image: bool, default_prompt: str) -> str:
    text = (prompt or "").strip()
    if text:
        return text
    if has_image:
        return default_prompt
    raise HTTPException(status_code=400, detail="prompt or image required")


def _resolve_codex_timeout(timeout_seconds: float | None) -> float:
    timeout = timeout_seconds if timeout_seconds is not None else _CODEX_TIMEOUT_SECONDS
    return max(1.0, min(float(timeout), _CODEX_TIMEOUT_SECONDS))


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(title="spark-gateway")

# Prometheus metrics — `/metrics` 노출.
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "service": "spark-gateway",
        "inference_models": list(_inference_models),
        "audio_routes": list(_audio_routes),
    }


# ── /v1/* OpenAI-compatible inference proxy ────────────────────────────────
@app.get("/v1/models", dependencies=[Depends(require_bearer)])
async def list_models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "owned_by": "spark-inference"}
            for name in sorted(_inference_models)
        ],
    }


async def _proxy_inference_by_model_field(request: Request, sub_path: str) -> StreamingResponse:
    body = await request.body()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON body") from exc
    model = payload.get("model")
    if not model:
        raise HTTPException(status_code=400, detail="`model` field required")
    base = _inference_models.get(model)
    if not base:
        raise HTTPException(
            status_code=404,
            detail=f"model {model!r} not registered (have: {sorted(_inference_models)})",
        )
    return await _proxy(request, f"{base}/v1/{sub_path}", body=body)


@app.post("/v1/chat/completions", dependencies=[Depends(require_bearer)])
async def chat_completions(request: Request) -> StreamingResponse:
    return await _proxy_inference_by_model_field(request, "chat/completions")


@app.post("/v1/completions", dependencies=[Depends(require_bearer)])
async def completions(request: Request) -> StreamingResponse:
    return await _proxy_inference_by_model_field(request, "completions")


@app.post("/v1/embeddings", dependencies=[Depends(require_bearer)])
async def embeddings(request: Request) -> StreamingResponse:
    return await _proxy_inference_by_model_field(request, "embeddings")


@app.post("/v1/rerank", dependencies=[Depends(require_bearer)])
async def rerank(request: Request) -> StreamingResponse:
    return await _proxy_inference_by_model_field(request, "rerank")


# ── /v1/codex Codex-backed image/prompt worker ────────────────────────────
@app.post("/v1/codex", dependencies=[Depends(require_bearer)])
async def codex_run(
    image: UploadFile | None = File(default=None),
    prompt: str | None = Form(default=None),
    timeout_seconds: float | None = Form(default=None),
) -> dict[str, str]:
    if not _CODEX_ENABLED:
        raise HTTPException(status_code=404, detail="codex endpoint is disabled")

    image_body, suffix = await _read_optional_codex_image(image)
    codex_prompt = _resolve_codex_prompt(
        prompt,
        has_image=image_body is not None,
        default_prompt=_CODEX_DEFAULT_PROMPT,
    )
    timeout = _resolve_codex_timeout(timeout_seconds)

    with tempfile.TemporaryDirectory(prefix="spark-codex-") as tmpdir:
        image_path: Path | None = None
        if image_body is not None and suffix is not None:
            image_path = Path(tmpdir) / f"input{suffix}"
            image_path.write_bytes(image_body)
        try:
            raw = await _run_codex_once(image_path, codex_prompt, timeout)
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "text": raw,
        "raw": raw,
        "engine": "codex-cli",
    }


@app.post("/v1/codex/stream", dependencies=[Depends(require_bearer)])
async def codex_stream(
    image: UploadFile | None = File(default=None),
    prompt: str | None = Form(default=None),
    timeout_seconds: float | None = Form(default=None),
) -> StreamingResponse:
    if not _CODEX_ENABLED:
        raise HTTPException(status_code=404, detail="codex endpoint is disabled")

    image_body, suffix = await _read_optional_codex_image(image)
    codex_prompt = _resolve_codex_prompt(
        prompt,
        has_image=image_body is not None,
        default_prompt=_CODEX_DEFAULT_PROMPT,
    )
    timeout = _resolve_codex_timeout(timeout_seconds)

    async def events() -> AsyncIterator[str]:
        with tempfile.TemporaryDirectory(prefix="spark-codex-") as tmpdir:
            image_path: Path | None = None
            if image_body is not None and suffix is not None:
                image_path = Path(tmpdir) / f"input{suffix}"
                image_path.write_bytes(image_body)
            try:
                async for line in _stream_codex_jsonl(image_path, codex_prompt, timeout):
                    yield _sse("codex", line)
            except TimeoutError as exc:
                yield _sse("error", json.dumps({"detail": str(exc)}))
                return
            except RuntimeError as exc:
                yield _sse("error", json.dumps({"detail": str(exc)}))
                return
            yield _sse("done", "{}")

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


# ── /v1/ocr compatibility alias ───────────────────────────────────────────
@app.post("/v1/ocr", dependencies=[Depends(require_bearer)])
async def codex_ocr(
    image: UploadFile = File(...),
    prompt: str | None = Form(default=None),
    timeout_seconds: float | None = Form(default=None),
) -> dict[str, str]:
    if not _CODEX_OCR_ENABLED:
        raise HTTPException(status_code=404, detail="codex OCR endpoint is disabled")

    image_body, suffix = await _read_codex_image(image)
    ocr_prompt = prompt or _CODEX_OCR_DEFAULT_PROMPT
    timeout = _resolve_codex_timeout(timeout_seconds)

    with tempfile.TemporaryDirectory(prefix="spark-codex-ocr-") as tmpdir:
        image_path = Path(tmpdir) / f"input{suffix}"
        image_path.write_bytes(image_body)
        try:
            raw = await _run_codex_ocr(image_path, ocr_prompt, timeout)
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "text": raw,
        "raw": raw,
        "engine": "codex-cli",
    }


# ── /v1/audio/* path-keyed proxy (multipart/binary OK) ────────────────────
def _make_audio_handler(target_url: str):
    async def handler(request: Request) -> StreamingResponse:
        return await _proxy(request, target_url)
    return handler


for _path, _target in _audio_routes.items():
    app.add_api_route(
        _path,
        _make_audio_handler(_target),
        methods=["POST"],
        dependencies=[Depends(require_bearer)],
        include_in_schema=True,
    )
