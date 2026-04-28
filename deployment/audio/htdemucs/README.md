# `audio/htdemucs`

Meta [htdemucs](https://github.com/facebookresearch/demucs) (Hybrid Transformer Demucs) — audio source separation. 한 곡 → drums / bass / vocals / other 4-stem.

## API

`POST /v1/audio/stems` — spark-gateway (default 10080) 너머로 호출.

```bash
KEY="$(grep -E '^GATEWAY_MASTER_KEY=' envs/networks/gateway/.env.local | cut -d= -f2-)"
curl -X POST \
  -H "Authorization: Bearer $KEY" \
  -F "audio=@song.wav" \
  --output stems.zip \
  http://127.0.0.1:10080/v1/audio/stems
unzip stems.zip
# drums.wav  bass.wav  other.wav  vocals.wav
```

응답은 `application/zip` — 4개 stem WAV 파일 묶음. 각 stem 은 원본과 동일한 샘플레이트/길이.

## 설계 노트

- **CUDA 가속** — `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` 베이스 + PyTorch cu129 휠 (`torch==2.9.1` / `torchaudio==2.9.1`). DGX Spark 의 sm_121 (Blackwell GB10) 에서 3-4s 클립 기준 cold ~2.2s (JIT 포함) → warm ~0.9-1.2s. CPU 전용 빌드(이전 v1) 대비 ~6-7x 가속.
- **cu129 인덱스를 쓰는 이유**: cu124 인덱스의 arm64 휠은 sm_50/80/86/89/90/90a SASS 만 들어 있어 sm_121 에서 `RuntimeError: no kernel image is available`. cu129 휠은 sm_120 PTX 를 포함해 sm_121 도 PTX JIT 로 통과 (vLLM 컨테이너의 torch 2.10.0+cu129 와 동일 라인).
- **베이스 12.4 ↔ wheel 12.9 mismatch 무해** — torch wheel 이 `nvidia-cuda-runtime-cu12==12.9.x` 로 자기 12.9 libs 를 동봉해 자체 사용.
- **모델 로드는 startup 시 한 번** — `get_model("htdemucs")` 로 만든 모델 객체를 모듈 로드 시 한 번 만들고 요청마다 재사용.
- **demucs API 선택**: 4.0.1 의 high-level `Separator` (`demucs.api`) 는 unreleased — main 에만 존재. lower-level `apply_model` / `AudioFile` 조합으로 직접 inference. WAV 출력은 stdlib `wave` 로 (torchaudio.save 가 신버전에서 torchcodec 의존하게 됨).
- **재현성**: `demucs==4.0.1` PyPI 핀, `torch==2.9.1`/`torchaudio==2.9.1` cu129 인덱스 핀. 모델 weights 는 첫 부팅 시 `~/.cache/torch/hub` 로 자동 다운로드.

## sm_121 (Blackwell) 호환성 메모

PyTorch 2.9.x 휠의 capability list 는 12.0 까지로 표시되어 startup 시 다음 경고 한 번 출력 (무해):

```
UserWarning: Found GPU0 NVIDIA GB10 which is of cuda capability 12.1.
Minimum and Maximum cuda capability supported by this version of PyTorch is (8.0) - (12.0)
```

cu129 휠에는 sm_120 PTX 가 포함되어 있어 sm_121 에서 PTX JIT 으로 컴파일 → 정상 동작. 첫 요청에서 JIT 컴파일 비용 (~1-2s) 발생, 이후 warm 호출은 ~0.9s. sm_121 SASS 가 정식 들어간 빌드 (PyTorch nightly 또는 NGC) 로 교체하면 JIT 비용도 사라짐 — 별도 follow-up 후보.

## 인증

게이트웨이(`networks/gateway`) 가 Bearer 검증 담당. 컴포넌트 자체에는 별도 auth 없음.

## 입력 포맷

ffmpeg + libsndfile1 베이스 → wav / mp3 / flac / m4a / ogg 모두 받음. 큰 파일도 multipart 스트리밍으로 디스크에 저장 후 처리.

## 트러블슈팅

- **CUDA OOM**: 매우 긴 곡 + 동시 요청 시 발생 가능. `apply_model(..., split=True)` 로 chunk 분리 가능 (현재 default 도 split=True). 그래도 부족하면 `HTDEMUCS_GPU_IDS` 로 더 큰 GPU 슬롯 지정.
- **CPU 폴백**: GPU 가용성이 없는 호스트에서는 `app/main.py` 의 `torch.cuda.is_available()` 체크가 자동으로 `cpu` 로 떨어짐. 단 베이스 이미지가 `nvidia/cuda` 이고 compose 가 `runtime: nvidia` 를 강제하므로 GPU 없는 호스트에선 컨테이너 부팅 자체가 안 됨 — 그런 호스트엔 별도 CPU 전용 Dockerfile 로 분기 필요.
- **첫 요청 지연**: 모델 weights 다운로드 (~80MB) + sm_121 PTX JIT 컴파일 (~1-2s) 이 첫 startup / 첫 요청에 일어남. 컨테이너 logs 에 `htdemucs model ready (samplerate=44100, sources=['drums','bass','other','vocals'])` 가 보이면 모델 로드는 끝, JIT 비용은 첫 inference 호출에서 한 번 발생.
