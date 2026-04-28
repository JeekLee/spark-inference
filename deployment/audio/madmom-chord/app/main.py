"""audio/madmom-chord — chord recognition via Madmom CNN+CRF.

Endpoint: POST /chords
  Auth: Authorization: Bearer <AUDIO_MASTER_KEY>
  Body: multipart/form-data with `audio` field (any format readable by
        ffmpeg/libsndfile — wav/mp3/flac/m4a/ogg).
  Response: {"chords": [{"start": float, "end": float, "chord": str}, ...]}
            chord 라벨 형식: "<root>:<quality>" (예: "C:maj", "E:min", "N").
            "N" 은 chord 가 없는 (silence/non-tonal) 구간.

모델은 startup 시 한 번 로드. 두 processor 모두 stateless 라 동시 호출
안전.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from madmom.features.chords import (
    CNNChordFeatureProcessor,
    CRFChordRecognitionProcessor,
)

logging.basicConfig(level=os.environ.get("MADMOM_CHORD_LOG_LEVEL", "INFO"))
log = logging.getLogger("madmom-chord")

_MASTER_KEY = os.environ.get("AUDIO_MASTER_KEY", "")
if not _MASTER_KEY:
    raise RuntimeError(
        "AUDIO_MASTER_KEY env var must be set — see envs/audio/madmom-chord/.env.example"
    )


async def require_bearer(authorization: str = Header(default="")) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    if authorization[len("Bearer "):] != _MASTER_KEY:
        raise HTTPException(status_code=401, detail="invalid master key")


app = FastAPI(title="madmom-chord — spark-inference audio service")

_features = CNNChordFeatureProcessor()
_recog = CRFChordRecognitionProcessor()


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "madmom-chord"}


@app.post("/chords", dependencies=[Depends(require_bearer)])
async def chords(audio: UploadFile = File(...)) -> dict[str, list[dict[str, object]]]:
    if not audio.filename:
        raise HTTPException(status_code=400, detail="audio.filename required")

    suffix = Path(audio.filename).suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        path = Path(tmp.name)
        while chunk := await audio.read(1 << 20):
            tmp.write(chunk)

    try:
        log.info("processing %s (%d bytes)", audio.filename, path.stat().st_size)
        feats = _features(str(path))
        result = _recog(feats)
        return {
            "chords": [
                {"start": float(start), "end": float(end), "chord": str(label)}
                for start, end, label in result
            ]
        }
    finally:
        path.unlink(missing_ok=True)
