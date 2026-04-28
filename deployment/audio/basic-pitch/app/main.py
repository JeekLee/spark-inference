"""basic-pitch — polyphonic pitch transcription via Spotify BasicPitch.

`POST /notes` 는 multipart 오디오를 받아 ICASSP 2022 모델로 전사하고
note 이벤트(start/end/pitch_midi/pitch_name/amplitude)를 JSON 으로 반환한다.

게이트웨이(`networks/gateway`) 가 인증 + 외부 노출 담당. 컴포넌트 자체는
internal docker network 만 노출 (compose 의 `ports:` 없음) — 자체 auth 불필요.

모델은 startup 시 한 번 로드 — TF graph 가 첫 호출에 lazy-init 되지 않게
`Model` 객체를 미리 만들어 두고 `predict()` 에 주입한다.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import Model, predict
from fastapi import FastAPI, File, HTTPException, UploadFile

logging.basicConfig(level=os.environ.get("BASIC_PITCH_LOG_LEVEL", "INFO"))
log = logging.getLogger("basic-pitch")

app = FastAPI(title="basic-pitch — spark-inference audio service")

log.info("loading BasicPitch model: %s", ICASSP_2022_MODEL_PATH)
_model = Model(ICASSP_2022_MODEL_PATH)
log.info("BasicPitch model ready")

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _midi_to_name(midi: int) -> str:
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "basic-pitch"}


@app.post("/notes")
async def notes(audio: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(audio.filename or "upload").suffix or ".wav"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await audio.read(1 << 20):
            tmp.write(chunk)

    try:
        try:
            _, _, note_events = predict(str(tmp_path), model_or_model_path=_model)
        except Exception as exc:
            log.exception("BasicPitch inference failed for %s", audio.filename)
            raise HTTPException(status_code=400, detail=f"transcription failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    notes_out = [
        {
            "start": float(start),
            "end": float(end),
            "pitch_midi": int(pitch_midi),
            "pitch_name": _midi_to_name(int(pitch_midi)),
            "amplitude": float(amplitude),
        }
        for start, end, pitch_midi, amplitude, _pitch_bends in note_events
    ]

    return {"notes": notes_out}
