"""htdemucs — source separation via Meta htdemucs.

`POST /stems` 는 multipart 오디오를 받아 4-stem(drums/bass/other/vocals)
으로 분리하고 zip 으로 묶어 반환한다.
`Authorization: Bearer <AUDIO_MASTER_KEY>` 헤더 필수.

모델은 startup 시 한 번 로드. v1 은 CPU only — torch.cuda.is_available()
가 True 면 자동으로 cuda 사용 (GPU 베이스 이미지로 빌드한 경우 대비).

demucs 4.0.1 의 high-level `Separator` API (`demucs.api`) 는 미릴리스
상태 (main 만 존재) 라 lower-level `apply_model` / `AudioFile` 조합으로
직접 inference. WAV 출력은 demucs `save_audio` (→ torchaudio.save) 가
torchaudio>=2.5 부터 torchcodec 을 필수로 끌어오므로 의존성 폭증 회피
위해 stdlib `wave` 로 직접 작성. samplerate / channels / sources
이름은 모델 객체에서 동적으로 가져온다.
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
import wave
import zipfile
from pathlib import Path

import numpy as np
import torch
from demucs.apply import apply_model
from demucs.audio import AudioFile
from demucs.pretrained import get_model
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

logging.basicConfig(level=os.environ.get("HTDEMUCS_LOG_LEVEL", "INFO"))
log = logging.getLogger("htdemucs")

_MASTER_KEY = os.environ.get("AUDIO_MASTER_KEY", "")
if not _MASTER_KEY:
    raise RuntimeError(
        "AUDIO_MASTER_KEY env var must be set — see envs/audio/htdemucs/.env.example"
    )


async def require_bearer(authorization: str = Header(default="")) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    if authorization[len("Bearer "):] != _MASTER_KEY:
        raise HTTPException(status_code=401, detail="invalid master key")


def _save_wav_pcm16(tensor: torch.Tensor, path: Path, samplerate: int) -> None:
    """Write a (channels, samples) float tensor as 16-bit PCM WAV.

    demucs 의 save_audio 는 torchaudio.save 를 거치는데 torchaudio>=2.5 부터
    .wav 저장에 torchcodec 의존성이 강제됨. 그 의존을 끊고 stdlib `wave` 로
    직접 작성. clip 은 [-1, 1] 로 한번 캡 후 int16 변환.
    """
    arr = tensor.detach().cpu().numpy().astype(np.float32, copy=False)
    if arr.ndim == 1:
        arr = arr[None]
    arr = np.clip(arr, -1.0, 1.0)
    int16 = (arr * 32767.0).astype("<i2")
    interleaved = int16.T.tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(arr.shape[0])
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(interleaved)


app = FastAPI(title="htdemucs — spark-inference audio service")

_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
log.info("loading htdemucs model on device=%s", _DEVICE)
_model = get_model("htdemucs")
_model.to(_DEVICE).eval()
_SAMPLERATE: int = _model.samplerate
_CHANNELS: int = _model.audio_channels
_SOURCES: list[str] = list(_model.sources)
log.info("htdemucs model ready (samplerate=%d, sources=%s)", _SAMPLERATE, _SOURCES)


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "htdemucs", "device": _DEVICE, "sources": _SOURCES}


@app.post("/stems", dependencies=[Depends(require_bearer)])
async def stems(audio: UploadFile = File(...)) -> StreamingResponse:
    suffix = Path(audio.filename or "upload").suffix or ".wav"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        in_path = Path(tmp.name)
        while chunk := await audio.read(1 << 20):
            tmp.write(chunk)

    try:
        try:
            wav = AudioFile(str(in_path)).read(
                streams=0, samplerate=_SAMPLERATE, channels=_CHANNELS,
            )
            ref = wav.mean(0)
            wav = wav - ref.mean()
            std = float(ref.std())
            if std > 0:
                wav = wav / std

            with torch.no_grad():
                sources = apply_model(
                    _model, wav[None], device=_DEVICE, progress=False, shifts=0,
                )[0]
            if std > 0:
                sources = sources * std
            sources = sources + ref.mean()
        except Exception as exc:
            log.exception("htdemucs failed for %s", audio.filename)
            raise HTTPException(status_code=400, detail=f"separation failed: {exc}") from exc

        with tempfile.TemporaryDirectory() as out_dir:
            out_root = Path(out_dir)
            stem_paths: dict[str, Path] = {}
            for stem_name, tensor in zip(_SOURCES, sources):
                stem_path = out_root / f"{stem_name}.wav"
                _save_wav_pcm16(tensor, stem_path, samplerate=_SAMPLERATE)
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
