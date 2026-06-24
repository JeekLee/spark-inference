# networks/gateway — spark-inference 단일 게이트웨이.
#
# 가벼운 FastAPI + httpx 프록시. multipart 그대로 forward, SSE 스트리밍 OK.
# vLLM / TEI 의 OpenAI-compatible /v1/* 와 audio 컴포넌트의 multipart/binary
# 엔드포인트를 한 포트(default 10080) 뒤에 통합.
FROM python:3.12-slim

ARG CODEX_CLI_VERSION=0.142.0

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g "@openai/codex@${CODEX_CLI_VERSION}" \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
