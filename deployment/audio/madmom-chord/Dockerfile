# audio/madmom-chord — Dockerfile
#
# Madmom (CPJKU) 의 chord recognition 파이프라인. CPU bound. ABI 안정성을
# 위해 Python 3.10 / numpy<2 / cython<3 를 핀하고 madmom 은 git 의 특정
# commit SHA 로 핀 설치 (PyPI 의 0.16.1 은 numpy>=1.20 / Python>=3.10 와
# 충돌하고, `@main` 은 재현성 X — SHA 로 박아 바이트 단위 고정).
#
# Image 크기: ~600MB (numpy/scipy/madmom + ffmpeg/libsndfile1).
FROM python:3.10-slim

# Madmom 핀 — CPJKU/madmom main HEAD (2024-08-25, Cython/NumPy 2 호환 패치 포함).
# 변경 시 https://github.com/CPJKU/madmom/commits/main 에서 신규 SHA 확인.
ARG MADMOM_COMMIT=27f032e8947204902c675e5e341a3faf5dc86dae

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 git build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/

# 1) 핀된 build deps 먼저 설치 — madmom 컴파일 시 ABI 호환을 위해.
# 2) 앱 deps 설치 (FastAPI 등).
# 3) madmom 은 핀된 SHA 로 --no-build-isolation 설치 (pre-installed
#    numpy/cython 재사용 → ABI 충돌 회피).
RUN pip install --no-cache-dir "numpy<2.0" "scipy" "cython<3.0" && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-build-isolation \
        "git+https://github.com/CPJKU/madmom.git@${MADMOM_COMMIT}"

COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
