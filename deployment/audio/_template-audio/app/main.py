"""Audio component template — replace with real model logic.

This stub responds to the placeholder endpoint with the upload size, so the
direct-exposure auth wiring can be validated without a model.

Auth: clients must send `Authorization: Bearer <AUDIO_MASTER_KEY>`. The key
is read from the `AUDIO_MASTER_KEY` env var at startup; missing/empty fails
boot. Same UX as LiteLLM's master key — set the same value across all
audio components for a single key across the audio surface.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile

_MASTER_KEY = os.environ.get("AUDIO_MASTER_KEY", "")
if not _MASTER_KEY:
    raise RuntimeError(
        "AUDIO_MASTER_KEY env var must be set — see "
        "envs/audio/__NAME__/.env.example"
    )


async def require_bearer(authorization: str = Header(default="")) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    if authorization[len("Bearer "):] != _MASTER_KEY:
        raise HTTPException(status_code=401, detail="invalid master key")


app = FastAPI(title="__NAME__ — spark-inference audio service")


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "__NAME__"}


@app.post("/__NAME__", dependencies=[Depends(require_bearer)])
async def __NAME__(audio: UploadFile = File(...)) -> dict[str, object]:
    size = 0
    while chunk := await audio.read(1 << 20):
        size += len(chunk)
    return {"received_bytes": size, "filename": audio.filename}
