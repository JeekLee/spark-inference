# `audio/basic-pitch`

Spotify [BasicPitch](https://github.com/spotify/basic-pitch) — polyphonic note transcription. audio → time-aligned MIDI 노트 이벤트.

## API

`POST /v1/audio/notes` — spark-gateway (default 10080) 너머로 호출.

```bash
KEY="$(grep -E '^GATEWAY_MASTER_KEY=' envs/networks/gateway/.env.local | cut -d= -f2-)"
curl -X POST \
  -H "Authorization: Bearer $KEY" \
  -F "audio=@clip.wav" \
  http://127.0.0.1:10080/v1/audio/notes
```

응답:

```json
{
  "notes": [
    {"start": 0.05, "end": 0.42, "pitch_midi": 60, "pitch_name": "C4", "amplitude": 0.81},
    {"start": 0.50, "end": 0.95, "pitch_midi": 64, "pitch_name": "E4", "amplitude": 0.74},
    ...
  ]
}
```

`pitch_midi` 는 MIDI 정수(0–127), `pitch_name` 은 표준 옥타브 표기 (`C4`=middle C). polyphonic 이라 동일 시점에 여러 notes 동시 등장 가능.

## 설계 노트

- **CPU only** — TF inference 는 노트 길이의 ~수배 속도로 빠름. GPU 자원 안 점유. madmom-chord / Qwen3-8B 와 같은 호스트 코로케이션 OK.
- **모델 로드는 startup 시 한 번** — `Model(ICASSP_2022_MODEL_PATH)` 를 모듈 로드 시 한 번 만들어두고 `predict()` 에 주입. lazy-init 으로 첫 요청 지연되는 일 없음.
- **재현성**: PyPI 패키지(basic-pitch==0.4.0) 가 모델 weights(ICASSP 2022) 를 동봉 — git pin 같은 외부 의존 없음.

## 인증

게이트웨이(`networks/gateway`) 가 Bearer 검증 담당. 컴포넌트 자체에는 별도 auth 없음.

## 입력 포맷

ffmpeg + libsndfile1 이 베이스 이미지에 들어 있어 wav / mp3 / flac / m4a / ogg 모두 받음. multipart 스트리밍으로 받아 디스크에 저장 후 처리.

## 트러블슈팅

- 비어있는/너무 짧은 클립: 노트 이벤트가 비어있는 응답 (`{"notes": []}`) 가능. 클라이언트 측에서 처리 필요.
- TF 메모리: TF 가 startup 시 ~500MB 메모리 잡음. 일반 운영엔 충분하지만 좁은 호스트에선 유의.
