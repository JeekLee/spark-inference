# Client API Reference

spark-gateway 가 노출하는 단일-포트 API. chat / embed / 오디오 분석 모두 한 키로 호출. 클라이언트 (M4L 백엔드, 스크립트, 다른 서비스) 가 이 문서만으로 통합 가능하도록 모은 reference.

> 게이트웨이 아키텍처 / 라우팅 메커니즘 / 트러블슈팅은 [`README.md`](README.md). 이 문서는 **API 호출자 입장**.

## 1. 접근 / 인증

```
Base URL:  http://127.0.0.1:10080      # 호스트 로컬 (default)
Auth:      Authorization: Bearer <GATEWAY_MASTER_KEY>
```

- 모든 라우트가 동일 키. 미동봉/불일치 → `401`.
- 게이트웨이 default = loopback. 외부 호출이 필요하면 호스트 운영자에게 `GATEWAY_BIND=0.0.0.0` + 방화벽 정책 요청.
- `GET /health`, `GET /metrics` 만 auth 면제.

## 2. 활성 모델 라인업

| 종류 | 이름 / path | 백엔드 |
|---|---|---|
| chat / instruct | `qwen3-8b` | Qwen3-8B BF16 (vLLM, GPU) |
| embedding | `bge-m3` | BAAI/bge-m3, 1024-d L2-normalized, multilingual (vLLM `--runner pooling`, GPU) |
| chord recognition | `/v1/audio/chords` | Madmom CNN+CRF (CPU) |
| note transcription | `/v1/audio/notes` | Spotify BasicPitch (CPU TF) |
| source separation | `/v1/audio/stems` | Meta htdemucs 4-stem (GPU CUDA) |

**gateway 의 책임 범위** = dedicated 모델 호스팅 + OpenAI-compat 라우팅. 음악 도메인 로직 (chord 표기 매핑, key detection, MIDI 분석, chord 진행 추천 등) 은 클라이언트 책임 — §10 참조.

매니페스트(`envs/_manifest.<target>.env`) 에 등재된 컴포넌트만 라우팅됨. `/v1/models` 또는 게이트웨이 logs 로 활성 set 확인 가능.

## 3. 엔드포인트

### 3-1. `GET /v1/models`

등록된 chat/embed 모델 목록.

```bash
curl -H "Authorization: Bearer $KEY" http://127.0.0.1:10080/v1/models
```

```json
{
  "object": "list",
  "data": [
    {"id": "qwen3-8b", "object": "model", "owned_by": "spark-inference"},
    {"id": "bge-m3",   "object": "model", "owned_by": "spark-inference"}
  ]
}
```

오디오 라우트는 OpenAI `/v1/models` 에 안 보임 (그쪽은 모델별 라우팅이 아니라 path 매칭). 활성 audio path 는 `GET /health` 또는 게이트웨이 startup logs 참조.

### 3-2. `POST /v1/chat/completions`

OpenAI 호환. 라우팅 키 = body 의 `model` 필드. SSE streaming (`stream: true`) 지원.

```bash
curl -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b",
    "messages": [{"role":"user","content":"Hello /no_think"}],
    "max_tokens": 100,
    "temperature": 0.4,
    "stream": false
  }' http://127.0.0.1:10080/v1/chat/completions
```

응답: 표준 OpenAI 포맷 (`choices[0].message.content`, `usage` 등).

> `qwen3-8b` 는 reasoning 모델 — prompt 끝에 `/no_think` 를 붙이면 reasoning 단계 생략하고 바로 답변 (latency 단축). reasoning 단계 응답이 필요하면 `choices[0].message.reasoning` 필드 활용.

### 3-3. `POST /v1/embeddings`

OpenAI 호환. 라우팅 키 = `model` 필드.

```bash
curl -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "bge-m3",
    "input": ["문장 A", "문장 B", "..."]
  }' http://127.0.0.1:10080/v1/embeddings
```

응답: `data[].embedding` (1024-d, L2-normalized 즉 `||v||₂ = 1`). cosine similarity = dot product.

multilingual — 한↔영 cross-lingual semantic 동일 의미 ≈ 0.85+, paraphrase ≈ 0.6+.

### 3-4. `POST /v1/audio/chords` — 코드 인식

multipart upload, JSON 응답.

```bash
curl -X POST -H "Authorization: Bearer $KEY" \
  -F "audio=@clip.wav" \
  http://127.0.0.1:10080/v1/audio/chords
```

```json
{
  "chords": [
    {"start": 0.0, "end": 1.5, "chord": "C:maj"},
    {"start": 1.5, "end": 3.0, "chord": "A:min"},
    {"start": 3.0, "end": 4.5, "chord": "N"}
  ]
}
```

- 라벨: `<root>:<quality>` (root: `A`–`G`, `#`/`b` 가능; quality: `maj` / `min`)
- `N` = no chord / silence / non-tonal
- `start`, `end`: 초 단위 float
- 합성 sine 같은 입력은 `N` 만 나올 수 있음 (실제 timbre 분포 기준 학습)

### 3-5. `POST /v1/audio/notes` — 노트 전사

multipart upload, JSON 응답. polyphonic OK.

```bash
curl -X POST -H "Authorization: Bearer $KEY" \
  -F "audio=@clip.wav" \
  http://127.0.0.1:10080/v1/audio/notes
```

```json
{
  "notes": [
    {"start": 0.05, "end": 0.42, "pitch_midi": 60, "pitch_name": "C4", "amplitude": 0.81},
    {"start": 0.05, "end": 0.42, "pitch_midi": 64, "pitch_name": "E4", "amplitude": 0.74}
  ]
}
```

- `pitch_midi`: int 0–127
- `pitch_name`: `C4` (middle C = MIDI 60), `A#3` 등 (sharp 만, flat 표기 X)
- `amplitude`: 0–1 float
- 동일 시점 다중 노트 가능 — 코드 분석 시 동시 시각의 노트들을 묶어서 활용

### 3-6. `POST /v1/audio/stems` — 소스 분리

multipart upload, **`application/zip` 응답** (binary).

```bash
curl -X POST -H "Authorization: Bearer $KEY" \
  -F "audio=@song.wav" \
  --output stems.zip \
  http://127.0.0.1:10080/v1/audio/stems

unzip stems.zip
# drums.wav  bass.wav  other.wav  vocals.wav
```

- 4개 stem 항상 모두 들어 있음 (silent stem 도 zero-rms wav 로 포함)
- 각 stem 의 samplerate / 길이 = 원본과 동일
- 입력 mono → 내부적으로 stereo upsample 처리됨

### 3-7. `GET /health`, `GET /metrics`

auth 면제. 운영용.

```bash
curl http://127.0.0.1:10080/health
# {"ok":true,"service":"spark-gateway","inference_models":["qwen3-8b","bge-m3"],"audio_routes":["/v1/audio/chords","/v1/audio/notes","/v1/audio/stems"]}

curl http://127.0.0.1:10080/metrics
# # HELP python_gc_objects_collected_total ...
# (Prometheus exposition format)
```

## 4. 입력 오디오 포맷

`/v1/audio/*` 모두 (multipart):

- ffmpeg + libsndfile1 베이스 — wav / mp3 / flac / m4a / ogg 받음
- mono / stereo 모두 OK (모델이 내부 변환)
- multipart `audio` 필드명 고정. `Content-Type: audio/...` 권장하지만 `application/octet-stream` 도 동작
- 사이즈 제한 명시 X (실용적으로는 GPU/메모리에 의해 제한)

## 5. 에러 / 상태 코드

| Status | 의미 | body |
|---|---|---|
| 200 | OK | (각 엔드포인트별 응답) |
| 400 | request 파싱 실패 (multipart `audio` 누락 등) | `{"detail": "..."}` |
| 401 | Authorization 누락 / 키 불일치 | `{"detail": "missing or malformed Authorization header"}` 또는 `"invalid master key"` |
| 404 | 모델/라우트 미등록 | `{"detail": "model 'foo' not registered (have: ['qwen3-8b','bge-m3'])"}` 등 |
| 502 | 백엔드 컨테이너 down / unreachable | `{"detail": "backend unreachable: ..."}` |
| 5xx | 모델 추론 실패 | 백엔드별 detail message |

5xx / 502 는 retry-with-backoff 권장 (모델 재기동 / 일시 OOM 등 transient 케이스 흡수).

## 6. 성능 특성 (DGX Spark 측정값)

| 호출 | latency |
|---|---|
| `/v1/chat/completions` (qwen3-8b, 100 토큰, no_think) | ~7s |
| `/v1/chat/completions` SSE TTFT | ~2-3s |
| `/v1/embeddings` (짧은 문장 5개) | ~50ms |
| `/v1/audio/chords` (4s 클립) | ~1s |
| `/v1/audio/notes` (4s 클립) | ~50ms |
| `/v1/audio/stems` (3-4s 클립) | cold ~2.2s, warm ~0.9-1.2s |

지표일 뿐 SLO 아님. 동시성 / 큐잉 정책은 명시적 보장 X (현재 단일 워커).

## 7. 클라이언트 라이브러리 호환

- **OpenAI Python SDK**: chat/embed 는 `OpenAI(base_url="http://127.0.0.1:10080/v1", api_key="<KEY>")` 그대로 호환. `/v1/audio/*` 는 SDK 가 모르는 path 라 별도 httpx/requests 호출.
- **OpenAPI 스펙**: 게이트웨이가 FastAPI 라 `/openapi.json`, Swagger UI `/docs` 자동 노출. codegen 으로 typed 클라이언트 생성 가능.

## 8. 빠른 검증

```bash
KEY="<발급받은 키>"
GW="http://127.0.0.1:10080"

# health
curl -s "$GW/health" | jq

# 활성 모델
curl -s -H "Authorization: Bearer $KEY" "$GW/v1/models" | jq

# chat
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"qwen3-8b","messages":[{"role":"user","content":"reply HELLO /no_think"}],"max_tokens":10,"temperature":0}' \
  "$GW/v1/chat/completions" | jq -r '.choices[0].message.content'

# embedding
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"bge-m3","input":["test"]}' "$GW/v1/embeddings" | jq '.data[0].embedding | length'
# → 1024

# audio (test wav 준비 후)
curl -s -X POST -H "Authorization: Bearer $KEY" -F "audio=@test.wav" "$GW/v1/audio/chords" | jq
curl -s -X POST -H "Authorization: Bearer $KEY" -F "audio=@test.wav" "$GW/v1/audio/notes" | jq
curl -s -X POST -H "Authorization: Bearer $KEY" -F "audio=@test.wav" --output /tmp/stems.zip "$GW/v1/audio/stems" \
  && unzip -l /tmp/stems.zip
```

## 9. 보장하지 않는 것

- 동시 호출 시 응답 순서 / 큐잉 정책
- latency SLO (위 표는 측정값일 뿐)
- 모델 가중치 / 설정 변경에 대한 backward compat — **모델 이름 (`qwen3-8b`, `bge-m3`) 은 변경 시 새 이름 부여**, 클라이언트는 응답 모델 ID 를 검증할 것
- 정확도 — 합성 오디오는 madmom 의 학습 분포 밖. 실 음원 기준 검증 권장

## 10. 도메인 로직은 클라이언트 책임

gateway 는 **dedicated 모델 호스팅 + OpenAI-compat 라우팅** 만 담당합니다. 음악 이론, 표기법 매핑, key detection, MIDI 분석, chord 진행 추천 등 **도메인 로직은 클라이언트 (M4L 사이드카, web BFF, s4l 등) 가 직접 구현**합니다.

원칙:
- gateway 컴포넌트 = 한 dedicated 모델 wrap (madmom, basic-pitch, htdemucs, vLLM 모델)
- 범용 LLM(`qwen3-8b`) 위에 도메인 prompt 를 박아 새 endpoint 를 노출하는 것은 ❌ — 그건 클라이언트/BFF 의 일

이 원칙에 따라 자주 발생하는 패턴을 아래에 정리합니다.

### 10-1. chord 표기 변환 (`<root>:<quality>` ↔ pop)

`/v1/audio/chords` 출력은 madmom 컨벤션 (`C:maj`, `A:min`, `N`).  
pop 표기 (`CM`, `Am`) 가 필요하면 클라이언트에서 매핑:

```ts
// ~30줄 매핑 테이블 (실 구현은 클라이언트 repo)
function toPop(label: string): string | null {
  if (label === "N") return null;                  // silence
  const [root, qual] = label.split(":");
  const Q: Record<string, string> = {
    maj: "M", min: "m", "7": "7", maj7: "M7", min7: "m7", dim: "dim", aug: "aug",
  };
  return root + (Q[qual] ?? qual);
}
```

연속된 동일 chord 합치기, `N` (silence) drop 도 클라이언트 책임.

### 10-2. chord 진행 추천 / 다음 코드 예측

dedicated chord-generation 모델은 인프라에서 제공하지 않습니다 (사전 PoC 결과 운영 부적합 — `text-chord-predictor` 출력 품질 ↓, `musiclang-chord-v2-4k` 라이브러리 broken). 대신 **클라이언트가 `/v1/chat/completions` 에 chord-domain system prompt + few-shot 으로 직접 호출**합니다.

권장 패턴 (LOC ~150 정도 클라이언트 모듈):

```jsonc
// system prompt 골자 (실 system 메시지에 그대로 사용 가능)
{
  "role": "system",
  "content": "You are a music theory expert. Output ONLY chord symbols on a single line, space-separated. No commentary. Use pop notation: A-G, optional #/b, quality (M, m, 7, M7, m7, m7b5, dim, aug, sus2, sus4), optional /bass."
}
```

```jsonc
// few-shot 예시 (assistant 응답 흉내)
{"role": "user", "content": "Continue this chord progression with 4 more chords:\nAm CM Dm E7"}
{"role": "assistant", "content": "Am Dm G7 CM"}
```

```jsonc
// 마지막 user 메시지: 실제 요청
{"role": "user", "content": "Continue this chord progression with 8 more chords:\nAm CM Dm E7"}
```

추가 사항:
- qwen3 는 thinking 모드라 `chat_template_kwargs: {"enable_thinking": false}` 필수 — 안 그러면 `content` 가 `null` 이고 모든 토큰이 `reasoning` 으로 소비
- 응답 파싱: `re.split(r"[\s,;|\-]+", raw)` 후 chord regex `^[A-G][#b]?(M7|m7b5|m7|M|m|7|dim|aug|o|sus2|sus4)?(/[A-G][#b]?)?$` 로 필터
- 측정 latency: nb_chords=8 시 ~850ms, nb_chords=16 시 ~2s, 그 이상은 비선형 (≤16 권장)
- key/exclude/validity 같은 추가 제약은 system prompt 에 박아넣는 식으로 클라이언트가 설계

### 10-3. key detection

별도 endpoint 없음. 클라이언트가 chord 진행 (`/v1/audio/chords` 결과 또는 사용자 입력) 을 `/v1/chat/completions` 에 던지고 "Identify the key of this chord progression" 류 프롬프트로 호출.

또는 client-side 라이브러리 (예: `music21.js` 의 simple-key 알고리즘) 를 직접 사용 — gateway 호출 자체를 안 해도 됨.

### 10-4. MIDI 분석

gateway 의 audio 라우트는 **multipart wav/mp3/...** 만 받음. MIDI 파일 직접 입력 라우트는 없음. 클라이언트가 MIDI 를 파싱 (예: `music21.js`, `midi-parser-js`) 하거나, MIDI → audio 렌더링 후 audio 라우트 호출.

---

위 패턴들은 모두 클라이언트 repo 의 ground truth (예: s4l 의 `src/shared/api/`) 에서 실 구현. 이 문서는 *gateway 가 제공하는 1차 surface* 의 spec 만 담당하고, 그 위 도메인 어댑터의 책임 경계와 권장 패턴을 §10 에 명시합니다.
