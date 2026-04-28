# audio/htdemucs — Dockerfile
#
# Meta htdemucs (Hybrid Transformer Demucs) — vocal/drums/bass/other 4-stem
# source separation. v1 은 CPU only — arm64+Blackwell+CUDA 베이스 이미지를
# 다듬는 작업과 분리해 라인업 부팅을 우선. GPU 가속은 별도 follow-up.
#
# torch CPU build 가 demucs 의 transitive dep 으로 들어와 이미지가 ~1.5GB
# 까지 부푼다. 모델 weights (htdemucs ~80MB) 는 첫 로드 때 ~/.cache 로
# 다운로드 — startup 시 한 번 lazy fetch 후 재사용.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
