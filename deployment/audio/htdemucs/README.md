# `audio/htdemucs`

Meta [htdemucs](https://github.com/facebookresearch/demucs) (Hybrid Transformer Demucs) — audio source separation. 한 곡 → drums / bass / vocals / other 4-stem.

## API

`POST /stems` — 호스트 포트 직접 노출 (`HTDEMUCS_HOST_PORT`, default 10083).

```bash
KEY="$(grep -E '^AUDIO_MASTER_KEY=' envs/audio/htdemucs/.env.local | cut -d= -f2-)"
curl -X POST \
  -H "Authorization: Bearer $KEY" \
  -F "audio=@song.wav" \
  --output stems.zip \
  http://127.0.0.1:10083/stems
unzip stems.zip
# drums.wav  bass.wav  other.wav  vocals.wav
```

응답은 `application/zip` — 4개 stem WAV 파일 묶음. 각 stem 은 원본과 동일한 샘플레이트/길이.

## 설계 노트

- **v1 은 CPU only** — arm64+Blackwell+CUDA 베이스 이미지 마이그레이션은 별도 PR 로 분리. 30s 클립 기준 CPU 분리 ~60s, GPU 활성 시 ~3s 예상 (DGX Spark sm_120).
- **모델 로드는 startup 시 한 번** — `get_model("htdemucs")` 로 만든 모델 객체를 모듈 로드 시 한 번 만들고 요청마다 재사용.
- **demucs API 선택**: 4.0.1 의 high-level `Separator` (`demucs.api`) 는 unreleased — main 에만 존재. lower-level `apply_model` / `AudioFile` / `save_audio` 조합으로 직접 inference.
- **재현성**: `demucs==4.0.1` PyPI 핀. 모델 weights 는 첫 부팅 시 `~/.cache/torch/hub` 로 자동 다운로드.

## 인증

Bearer auth — startup 시 `AUDIO_MASTER_KEY` env var 필수, 미설정/공백이면 boot 거부. LiteLLM 의 `LITELLM_MASTER_KEY` 와 같은 값으로 설정하면 클라이언트는 한 키로 chat/embed + audio 양쪽 호출 가능.

## 입력 포맷

ffmpeg + libsndfile1 베이스 → wav / mp3 / flac / m4a / ogg 모두 받음. 큰 파일도 multipart 스트리밍으로 디스크에 저장 후 처리.

## GPU 활성화 (follow-up 예정)

CPU 처리 속도가 부족해질 경우 다음 단계:
1. Dockerfile 베이스를 `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` 로 교체 + Python 3.11 + torch CUDA 빌드 설치
2. docker-compose.yml 에 `runtime: nvidia` + `NVIDIA_VISIBLE_DEVICES` 활성
3. envs/.env 에 `HTDEMUCS_GPU_IDS` 세팅

`app/main.py` 는 `torch.cuda.is_available()` 자동 감지 — 코드 수정 불필요.

## 트러블슈팅

- **OOM (CPU)**: 긴 곡(>5분) 분리 시 메모리 ~6GB 사용. 호스트 RAM 충분한지 확인.
- **첫 요청 지연**: 모델 weights 다운로드(80MB) 가 첫 startup 에 일어남. 컨테이너 logs 확인.
