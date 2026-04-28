"""Audio component template — replace with real model logic.

This stub responds to the placeholder endpoint with the upload size, so the
gateway pass-through wiring can be validated end-to-end without a model.
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
