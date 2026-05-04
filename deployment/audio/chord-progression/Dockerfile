# audio/chord-progression — Dockerfile
#
# qwen3-8b 를 chord-recommendation 도메인 프롬프트로 wrap 하는 thin proxy.
# 로컬 추론 X — httpx 로 같은 network 의 vLLM 백엔드(`qwen3-8b:8000`) 호출.
# 따라서 torch/transformers/CUDA 의존 없음.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
