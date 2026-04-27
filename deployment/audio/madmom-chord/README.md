# `audio/madmom-chord`

Madmom (CPJKU) 의 CNN+CRF chord recognition 파이프라인 — audio → time-aligned major/minor chord labels.

## API

`POST /audio/chords` (LiteLLM 게이트웨이 너머):

```bash
KEY="$(grep -E '^LITELLM_MASTER_KEY=' envs/networks/litellm/.env.local | cut -d= -f2-)"
curl -X POST \
  -H "Authorization: Bearer $KEY" \
  -F "audio=@clip.wav" \
  http://127.0.0.1:10080/audio/chords
```

응답:

```json
{
  "chords": [
    {"start": 0.0, "end": 1.5, "chord": "C:maj"},
    {"start": 1.5, "end": 3.0, "chord": "A:min"},
    ...
  ]
}
```

라벨 형식 `<root>:<quality>` — root 는 `A`–`G` (`#`/`b` 포함), quality 는 `maj` / `min`. silence/non-tonal 구간은 `N`.

## 설계 노트

- **CPU only** — Madmom 은 numpy/scipy 기반. GPU 사용 X. Qwen3-8B 와 같은 호스트에 코로케이션해도 GPU 자원 경쟁 없음.
- **모델 로드는 startup 시 한 번** — `CNNChordFeatureProcessor` / `CRFChordRecognitionProcessor` 두 processor 모두 stateless 라 동시 호출 안전 (FastAPI worker 다중도 OK).
- **의존성 핀**: numpy<2.0, cython<3.0, Python 3.10 — Madmom 0.16.1 (PyPI) 는 numpy>=1.20 / Python>=3.10 와 충돌. 대신 git 의 특정 commit SHA 로 핀 설치 (`Dockerfile::MADMOM_COMMIT`). 재현성 + 외부 코드 무결성 양쪽 다 잡음. ABI 안정성 위해 build deps 명시.

## 입력 포맷

ffmpeg + libsndfile1 이 베이스 이미지에 들어 있어 wav / mp3 / flac / m4a / ogg 모두 받음. 큰 파일은 multipart 스트리밍으로 받아 디스크에 저장 후 처리.

## 트러블슈팅

- 빌드 실패 (`madmom` cython 컴파일): `--no-build-isolation` 이 빠지면 madmom 이 자기만의 numpy 를 가져오면서 ABI 어긋남. Dockerfile 의 두 단계 install 순서를 보존할 것.
- 매우 짧은 클립 (< 1초): CRF 가 빈 결과 반환할 수 있음. 클라이언트에서 빈 chords 배열 처리 필요.
