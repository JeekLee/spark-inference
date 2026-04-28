# `networks/gateway`

spark-inference 단일 게이트웨이. FastAPI + httpx, 한 포트(default 10080) 뒤에 chat/embed (vLLM/TEI) + audio (multipart/binary) 통합.

## 왜 LiteLLM 이 아니라 자체 게이트웨이?

LiteLLM v1.82.3 의 `pass_through_endpoints` 는 라우트 시그니처에 `custom_body: Optional[dict]` 가 박혀 있어 FastAPI 가 모든 요청 body 를 JSON dict 로 파싱 시도. multipart/form-data 바이트는 dict_type 검증 실패 → 422/500. 우리 라인업은 단일 호스트 + 자체 호스팅 모델뿐이라 LiteLLM 의 multi-provider/load-balancer/cost-tracker 가치가 거의 없음. 직접 짜는 비용 ≈ httpx 프록시 ~150 LOC. 그래서 자체 구현.

## 라우팅 모델

요청 종류에 따라 다른 라우팅 키:

| 라우트 | 라우팅 키 | 매핑 |
|---|---|---|
| `/v1/chat/completions` | request body 의 `model` 필드 | `inference_models[model]` 의 base URL + `/v1/chat/completions` |
| `/v1/completions` | 동일 | `… + /v1/completions` |
| `/v1/embeddings` | 동일 | `… + /v1/embeddings` |
| `/v1/models` | 자체 응답 | 등록된 inference 모델 목록 |
| `/v1/audio/chords`, `/v1/audio/notes`, `/v1/audio/stems`, … | path 정확 매치 | `audio_routes[path]` 의 target URL |
| `/health`, `/metrics` | (auth 면제) | 게이트웨이 자체 |

## 매니페스트 = 라우팅

각 백엔드 컴포넌트가 자기 디렉토리에 `gateway.yaml` fragment 를 둠:

```yaml
# deployment/inferences/qwen3-8b/gateway.yaml
- kind: inference
  model: qwen3-8b
  url: http://qwen3-8b:8000
```

```yaml
# deployment/audio/madmom-chord/gateway.yaml
- kind: audio
  path: /v1/audio/chords
  target: http://madmom-chord:8000/chords
```

`render.sh` 는 `_manifest.<target>.env::INFERENCES` + `::AUDIO` 에 등재된 컴포넌트의 fragment 만 모아 `routes.rendered.yaml` 로 만들고, gateway 컨테이너가 이걸 startup 시 한 번 읽음.

매니페스트에서 빠진 컴포넌트는 `/v1/models` 응답에도 안 보이고 `/v1/audio/*` path 도 등록 안 됨 → 부팅 set 와 라우팅 surface 가 항상 일치 (drift 원천 차단).

## 인증

`GATEWAY_MASTER_KEY` env var 필수 — 미설정/공백이면 boot 거부 (compose `:?` 가드 + Python `RuntimeError` 양쪽). 모든 비-health/비-metrics 라우트가 `Authorization: Bearer <key>` 검증.

```bash
KEY=$(grep -E '^GATEWAY_MASTER_KEY=' envs/networks/gateway/.env.local | cut -d= -f2-)
curl -H "Authorization: Bearer $KEY" http://127.0.0.1:10080/v1/models
```

## 메트릭

`prometheus-fastapi-instrumentator` 로 `/metrics` 노출. 스크레이프 시 라우트별 latency / status / count 자동 수집. (auth 면제 — 메트릭 스크레이퍼가 별도 키 안 가지고 접근 가능. 외부 노출 시점에는 `GATEWAY_BIND` 가 loopback 인지 확인할 것.)

## 트러블슈팅

- **/v1/* 가 404**: 매니페스트에 모델 컴포넌트 등재됐는지 확인 → `make local-restart` 로 라우트 재렌더.
- **/v1/audio/* 가 404**: 마찬가지로 `_manifest.<target>.env::AUDIO` 등재 확인. 부팅 시 gateway 로그에 등록된 라우트 목록 출력.
- **502 backend unreachable**: 백엔드 컨테이너 down. `docker ps` / `make local-logs-c C=<name>`.
- **multipart 가 깨짐**: gateway 가 body 를 read 하는 시점에 boundary 가 보존되는지 확인. `Content-Type` 헤더 그대로 forward 하므로 정상이어야 함. 실패 시 백엔드 로그에서 raw body 확인.
