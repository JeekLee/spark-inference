"""Audio component template — replace with real model logic.

This stub responds to the placeholder endpoint with the upload size, so the
gateway routing can be validated end-to-end without a model.

게이트웨이(`networks/gateway`) 가 인증 + 외부 노출 담당. 컴포넌트 자체는
internal docker network 만 노출 (compose 의 `ports:` 없음) — 자체 auth 불필요.
"""
from __future__ import annotations

from fastapi import FastAPI, File, UploadFile

app = FastAPI(title="__NAME__ — spark-inference audio service")


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "__NAME__"}


@app.post("/__NAME__")
async def __NAME__(audio: UploadFile = File(...)) -> dict[str, object]:
    size = 0
    while chunk := await audio.read(1 << 20):
        size += len(chunk)
    return {"received_bytes": size, "filename": audio.filename}
