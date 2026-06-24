from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi.testclient import TestClient


PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-image-data"
AUTH = {"Authorization": "Bearer test-secret"}


def load_gateway(monkeypatch, tmp_path: Path, *, enabled: bool = True, max_bytes: int = 1024):
    routes_path = tmp_path / "routes.yaml"
    routes_path.write_text("backends: []\n", encoding="utf-8")

    monkeypatch.setenv("GATEWAY_MASTER_KEY", "test-secret")
    monkeypatch.setenv("GATEWAY_ROUTES_PATH", str(routes_path))
    monkeypatch.setenv("GATEWAY_CODEX_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("GATEWAY_CODEX_OCR_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("GATEWAY_CODEX_MAX_IMAGE_BYTES", str(max_bytes))
    monkeypatch.setenv("GATEWAY_CODEX_OCR_MAX_BYTES", str(max_bytes))
    monkeypatch.setenv("GATEWAY_CODEX_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("GATEWAY_CODEX_OCR_TIMEOUT_SECONDS", "30")

    sys.modules.pop("deployment.networks.gateway.app.main", None)
    return importlib.import_module("deployment.networks.gateway.app.main")


def post_ocr(client: TestClient, *, headers: dict[str, str] | None = None, content: bytes = PNG_BYTES):
    return client.post(
        "/v1/ocr",
        headers=headers or AUTH,
        files={"image": ("ocr.png", content, "image/png")},
        data={"prompt": "extract text", "timeout_seconds": "5"},
    )


def post_codex(
    client: TestClient,
    *,
    headers: dict[str, str] | None = None,
    prompt: str = "analyze this image",
    content: bytes | None = PNG_BYTES,
):
    files = {}
    if content is not None:
        files["image"] = ("codex.png", content, "image/png")
    return client.post(
        "/v1/codex",
        headers=headers or AUTH,
        files=files,
        data={"prompt": prompt, "timeout_seconds": "5"},
    )


def test_ocr_requires_bearer(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)
    client = TestClient(gateway.app)

    response = client.post(
        "/v1/ocr",
        files={"image": ("ocr.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 401


def test_ocr_returns_404_when_disabled(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=False)
    client = TestClient(gateway.app)

    response = post_ocr(client)

    assert response.status_code == 404
    assert response.json()["detail"] == "codex OCR endpoint is disabled"


def test_ocr_success_uses_uploaded_image_and_prompt(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)
    calls: list[dict[str, Any]] = []

    async def fake_run(image_path: Path, prompt: str, timeout_seconds: float) -> str:
        calls.append(
            {
                "image_path": image_path,
                "prompt": prompt,
                "timeout_seconds": timeout_seconds,
                "image_exists": image_path.exists(),
                "image_bytes": image_path.read_bytes(),
            }
        )
        return "HELLO\nWORLD"

    monkeypatch.setattr(gateway, "_run_codex_ocr", fake_run)
    client = TestClient(gateway.app)

    response = post_ocr(client)

    assert response.status_code == 200
    assert response.json() == {
        "text": "HELLO\nWORLD",
        "raw": "HELLO\nWORLD",
        "engine": "codex-cli",
    }
    assert calls == [
        {
            "image_path": calls[0]["image_path"],
            "prompt": "extract text",
            "timeout_seconds": 5.0,
            "image_exists": True,
            "image_bytes": PNG_BYTES,
        }
    ]
    assert not calls[0]["image_path"].exists()


def test_ocr_rejects_unsupported_image_type(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)
    client = TestClient(gateway.app)

    response = client.post(
        "/v1/ocr",
        headers=AUTH,
        files={"image": ("ocr.gif", b"GIF89a", "image/gif")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported image content type: image/gif"


def test_ocr_rejects_oversized_upload(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True, max_bytes=4)
    client = TestClient(gateway.app)

    response = post_ocr(client, content=b"12345")

    assert response.status_code == 413
    assert response.json()["detail"] == "image exceeds max size of 4 bytes"


def test_ocr_maps_codex_timeout_to_504(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)

    async def fake_run(image_path: Path, prompt: str, timeout_seconds: float) -> str:
        raise TimeoutError("codex OCR timed out")

    monkeypatch.setattr(gateway, "_run_codex_ocr", fake_run)
    client = TestClient(gateway.app)

    response = post_ocr(client)

    assert response.status_code == 504
    assert response.json()["detail"] == "codex OCR timed out"


def test_ocr_maps_codex_failure_to_502(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)

    async def fake_run(image_path: Path, prompt: str, timeout_seconds: float) -> str:
        raise RuntimeError("codex failed: invalid credentials")

    monkeypatch.setattr(gateway, "_run_codex_ocr", fake_run)
    client = TestClient(gateway.app)

    response = post_ocr(client)

    assert response.status_code == 502
    assert response.json()["detail"] == "codex failed: invalid credentials"


def test_codex_requires_bearer(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)
    client = TestClient(gateway.app)

    response = client.post("/v1/codex", data={"prompt": "hello"})

    assert response.status_code == 401


def test_codex_returns_404_when_disabled(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=False)
    client = TestClient(gateway.app)

    response = post_codex(client)

    assert response.status_code == 404
    assert response.json()["detail"] == "codex endpoint is disabled"


def test_codex_success_accepts_image_and_prompt(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)
    calls: list[dict[str, Any]] = []

    async def fake_run(image_path: Path | None, prompt: str, timeout_seconds: float) -> str:
        assert image_path is not None
        calls.append(
            {
                "image_path": image_path,
                "prompt": prompt,
                "timeout_seconds": timeout_seconds,
                "image_exists": image_path.exists(),
                "image_bytes": image_path.read_bytes(),
            }
        )
        return "analysis result"

    monkeypatch.setattr(gateway, "_run_codex_once", fake_run)
    client = TestClient(gateway.app)

    response = post_codex(client, prompt="describe the diagram")

    assert response.status_code == 200
    assert response.json() == {
        "text": "analysis result",
        "raw": "analysis result",
        "engine": "codex-cli",
    }
    assert calls[0]["prompt"] == "describe the diagram"
    assert calls[0]["timeout_seconds"] == 5.0
    assert calls[0]["image_exists"] is True
    assert calls[0]["image_bytes"] == PNG_BYTES
    assert not calls[0]["image_path"].exists()


def test_codex_success_accepts_text_only_prompt(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)
    calls: list[dict[str, Any]] = []

    async def fake_run(image_path: Path | None, prompt: str, timeout_seconds: float) -> str:
        calls.append(
            {
                "image_path": image_path,
                "prompt": prompt,
                "timeout_seconds": timeout_seconds,
            }
        )
        return "text response"

    monkeypatch.setattr(gateway, "_run_codex_once", fake_run)
    client = TestClient(gateway.app)

    response = post_codex(client, prompt="answer briefly", content=None)

    assert response.status_code == 200
    assert response.json()["text"] == "text response"
    assert calls == [
        {
            "image_path": None,
            "prompt": "answer briefly",
            "timeout_seconds": 5.0,
        }
    ]


def test_codex_rejects_empty_prompt_without_image(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)
    client = TestClient(gateway.app)

    response = client.post(
        "/v1/codex",
        headers=AUTH,
        data={"prompt": ""},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "prompt or image required"


def test_codex_command_places_prompt_before_variadic_image_option(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)
    image_path = tmp_path / "screen.png"

    cmd = gateway._build_codex_cmd(image_path, "read this image")

    assert cmd.index("read this image") < cmd.index("--image")


def test_codex_stream_sends_jsonl_as_sse(monkeypatch, tmp_path):
    gateway = load_gateway(monkeypatch, tmp_path, enabled=True)
    calls: list[dict[str, Any]] = []

    async def fake_stream(
        image_path: Path | None,
        prompt: str,
        timeout_seconds: float,
    ) -> AsyncIterator[str]:
        assert image_path is not None
        calls.append(
            {
                "image_path": image_path,
                "prompt": prompt,
                "timeout_seconds": timeout_seconds,
                "image_exists": image_path.exists(),
                "image_bytes": image_path.read_bytes(),
            }
        )
        yield '{"type":"item.completed","text":"partial"}'
        yield '{"type":"turn.completed"}'

    monkeypatch.setattr(gateway, "_stream_codex_jsonl", fake_stream)
    client = TestClient(gateway.app)

    response = client.post(
        "/v1/codex/stream",
        headers=AUTH,
        files={"image": ("codex.png", PNG_BYTES, "image/png")},
        data={"prompt": "stream this", "timeout_seconds": "5"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: codex\ndata: {"type":"item.completed","text":"partial"}' in response.text
    assert 'event: codex\ndata: {"type":"turn.completed"}' in response.text
    assert "event: done\ndata: {}" in response.text
    assert calls[0]["prompt"] == "stream this"
    assert calls[0]["timeout_seconds"] == 5.0
    assert calls[0]["image_exists"] is True
    assert calls[0]["image_bytes"] == PNG_BYTES
    assert not calls[0]["image_path"].exists()
