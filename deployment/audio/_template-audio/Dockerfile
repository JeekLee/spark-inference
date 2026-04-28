# Audio component template — FastAPI base.
#
# 각 audio 컴포넌트는 이 Dockerfile 을 복사한 뒤, requirements.txt 에 모델
# 의존성(librosa, madmom, basic-pitch, demucs 등)을 추가하고 app/main.py 에
# 실제 처리 로직을 구현한다.
#
# 베이스에 ffmpeg + libsndfile1 이 들어 있어 multipart 오디오 디코딩
# (wav/mp3/flac/m4a) 이 즉시 가능하다.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
