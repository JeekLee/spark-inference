from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


AUTH = {"Authorization": "Bearer test-secret"}


def load_gateway(monkeypatch, tmp_path: Path):
    routes_path = tmp_path / "routes.yaml"
    routes_path.write_text(
        """
backends:
  - kind: inference
    model: qwen3-reranker-0.6b
    url: http://reranker:8000
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("GATEWAY_MASTER_KEY", "test-secret")
    monkeypatch.setenv("GATEWAY_ROUTES_PATH", str(routes_path))
    monkeypatch.setenv("GATEWAY_CODEX_ENABLED", "false")

    sys.modules.pop("deployment.networks.gateway.app.main", None)
    return importlib.import_module("deployment.networks.gateway.app.main")


def test_rerank_requires_bearer(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path)
    client = TestClient(gateway.app)

    response = client.post(
        "/v1/rerank",
        json={
            "model": "qwen3-reranker-0.6b",
            "query": "hello",
            "documents": ["hello world"],
        },
    )

    assert response.status_code == 401


def test_rerank_routes_by_model_field(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path)
    calls: list[dict[str, Any]] = []

    async def fake_proxy(request: Request, sub_path: str):
        calls.append(
            {
                "sub_path": sub_path,
                "payload": json.loads((await request.body()).decode("utf-8")),
            }
        )
        return JSONResponse({"ok": True, "results": [{"index": 0, "relevance_score": 0.99}]})

    monkeypatch.setattr(gateway, "_proxy_inference_by_model_field", fake_proxy)
    client = TestClient(gateway.app)

    response = client.post(
        "/v1/rerank",
        headers=AUTH,
        json={
            "model": "qwen3-reranker-0.6b",
            "query": "local vision model",
            "documents": ["Qwen3-VL handles screenshots.", "BasicPitch handles audio."],
            "top_n": 1,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "results": [{"index": 0, "relevance_score": 0.99}]}
    assert calls == [
        {
            "sub_path": "rerank",
            "payload": {
                "model": "qwen3-reranker-0.6b",
                "query": "local vision model",
                "documents": ["Qwen3-VL handles screenshots.", "BasicPitch handles audio."],
                "top_n": 1,
            },
        }
    ]
