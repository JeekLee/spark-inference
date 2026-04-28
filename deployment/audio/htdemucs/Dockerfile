# audio/htdemucs — Dockerfile (GPU build)
#
# Meta htdemucs (Hybrid Transformer Demucs) — vocal/drums/bass/other 4-stem
# source separation. CUDA 가속 빌드.
#
# 베이스: nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 (multi-arch, OSS Docker
# Hub) — DGX Spark 의 sm_12.1(Blackwell GB10) 와 호환. CUDA 12.4 runtime +
# cudnn 9. Python 은 직접 설치.
#
# torch / torchaudio 는 PyTorch 의 cu129 인덱스에서 pull — Blackwell sm_120
# PTX 가 들어간 휠이 거기 있음 (cu124 휠은 sm_50/80/86/89/90/90a 만 → sm_121
# 에서 "no kernel image" 런타임 에러). vLLM 컨테이너가 동일하게 cu129 패밀리
# (torch 2.10.0+cu129) 로 정상 동작하는 것을 검증했고, 우리는 데이터 호환성
# 위해 같은 cu129 라인의 안정 버전 (2.9.1) 으로 핀.
#
# CUDA runtime 은 torch wheel 에 동봉되는 nvidia-cuda-runtime-cu12 가
# 가져오므로 베이스 이미지의 CUDA 12.4 와 mismatch 해도 OK — torch 가
# 자기 cuda 12.9 libs 를 자체 사용.
#
# 모델 weights (htdemucs ~80MB) 는 첫 부팅 때 ~/.cache/torch/hub 로 lazy
# fetch.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
        ffmpeg libsndfile1 \
        ca-certificates \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/

# torch / torchaudio 는 cu124 인덱스에서 (arm64 CUDA 휠 publish 되는 경로).
# demucs 는 PyPI default 에서. 둘을 별도 호출로 install — pip 는 단일 실행
# 안에서 여러 index URL 을 일관성 있게 처리하지 않음 (transitive deps 가
# 잘못된 인덱스에서 다시 풀 수 있음).
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cu129 \
        torch==2.9.1 torchaudio==2.9.1 \
    && pip install --no-cache-dir -r requirements.txt

COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
