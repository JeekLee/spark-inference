# audio/basic-pitch — Dockerfile
#
# Spotify BasicPitch — polyphonic pitch transcription. CPU bound.
# PyPI 패키지(basic-pitch) 가 직접 모델 weights(ICASSP 2022, ~17MB) 까지
# 동봉하므로 git pin 같은 외부 의존 없음. 단 TensorFlow(~500MB) 가 베이스
# 이미지 위에 깔리는 점 유의 (총 이미지 ~1.2GB).
#
# Python 3.11 — TF 2.16 가 3.12 도 지원하지만 arm64 wheel 안정성 면에서
# 3.11 이 더 검증됨. madmom-chord(3.10) 와 호환 핀 동기화 부담 없음 (각
# 컴포넌트 독립 이미지).
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
