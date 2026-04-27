"""audio/madmom-chord — chord recognition via Madmom CNN+CRF.

Endpoint: POST /chords
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

from fastapi import FastAPI, File, HTTPException, UploadFile
from madmom.features.chords import (
    CNNChordFeatureProcessor,
    CRFChordRecognitionProcessor,
)

logging.basicConfig(level=os.environ.get("MADMOM_CHORD_LOG_LEVEL", "INFO"))
log = logging.getLogger("madmom-chord")

app = FastAPI(title="madmom-chord — spark-inference audio service")

_features = CNNChordFeatureProcessor()
_recog = CRFChordRecognitionProcessor()


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "madmom-chord"}


@app.post("/chords")
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
