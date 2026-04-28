"""htdemucs — source separation via Meta htdemucs.

`POST /stems` 는 multipart 오디오를 받아 4-stem(drums/bass/other/vocals)
으로 분리하고 zip 으로 묶어 반환한다.

모델은 startup 시 한 번 로드. v1 은 CPU only — torch.cuda.is_available()
가 True 면 자동으로 cuda 사용 (GPU 베이스 이미지로 빌드한 경우 대비).
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
import zipfile
from pathlib import Path

import torch
from demucs.api import Separator
from demucs.audio import save_audio
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

logging.basicConfig(level=os.environ.get("HTDEMUCS_LOG_LEVEL", "INFO"))
log = logging.getLogger("htdemucs")

app = FastAPI(title="htdemucs — spark-inference audio service")

_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
log.info("loading htdemucs model on device=%s", _DEVICE)
_separator = Separator(model="htdemucs", device=_DEVICE)
log.info("htdemucs model ready (samplerate=%d)", _separator.samplerate)


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "htdemucs", "device": _DEVICE}


@app.post("/stems")
async def stems(audio: UploadFile = File(...)) -> StreamingResponse:
    suffix = Path(audio.filename or "upload").suffix or ".wav"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        in_path = Path(tmp.name)
        while chunk := await audio.read(1 << 20):
            tmp.write(chunk)

    try:
        try:
            _, separated = _separator.separate_audio_file(str(in_path))
        except Exception as exc:
            log.exception("htdemucs failed for %s", audio.filename)
            raise HTTPException(status_code=400, detail=f"separation failed: {exc}") from exc

        with tempfile.TemporaryDirectory() as out_dir:
            out_root = Path(out_dir)
            stem_paths: dict[str, Path] = {}
            for stem_name, tensor in separated.items():
                stem_path = out_root / f"{stem_name}.wav"
                save_audio(tensor, stem_path, samplerate=_separator.samplerate)
                stem_paths[stem_name] = stem_path

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
                for stem_name, stem_path in stem_paths.items():
                    zf.write(stem_path, arcname=f"{stem_name}.wav")
            buf.seek(0)
    finally:
        in_path.unlink(missing_ok=True)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="stems.zip"'},
    )
