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

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
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
    network 만 보임). `content-length` 는 httpx 가 다시 계산.
    """
    drop = {"host", "authorization", "content-length", "connection"}
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
