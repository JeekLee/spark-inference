# networks/gateway — spark-inference 단일 게이트웨이.
#
# 가벼운 FastAPI + httpx 프록시. multipart 그대로 forward, SSE 스트리밍 OK.
# vLLM / TEI 의 OpenAI-compatible /v1/* 와 audio 컴포넌트의 multipart/binary
# 엔드포인트를 한 포트(default 10080) 뒤에 통합.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
