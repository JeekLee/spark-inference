# spark-inference

DGX Spark(GB10/arm64) 단일 호스트에서 **OpenAI-compat 추론 모델** (vLLM/TEI 기반 chat/embed) + **FastAPI 오디오 모델** (multipart/binary) 을 띄우고 자체 **spark-gateway** (FastAPI + httpx) 한 포트(default `127.0.0.1:10080`) 로 통합 노출하는 인프라.

클라이언트는 단일 Bearer 키로 OpenAI 컨벤션의 `/v1/{chat/completions, embeddings, models}` 와 `/v1/audio/{chords, notes, stems, ...}` 모두 호출.

## 구조

```
spark-inference/
├── Makefile                        # make local-up / local-down / local-ps ...
├── deployment/                     # 배포 설정 — 어떻게 띄울지
│   ├── _run.sh                     # 매니페스트 기반 오케스트레이터
│   ├── inferences/
│   │   ├── _template-vllm/         # vLLM 컴포넌트 템플릿 (복사해서 사용)
│   │   └── _template-tei/          # TEI 컴포넌트 템플릿 (복사해서 사용)
│   ├── audio/
│   │   └── _template-audio/        # FastAPI 오디오 컴포넌트 템플릿
│   └── networks/
│       └── gateway/                # 자체 게이트웨이 (chat/embed + audio 통합, port 10080)
└── envs/                           # 환경변수 — 무엇을 띄울지 / 호스트별 값
    ├── _manifest.example.env       # 호스트별 부팅 매니페스트 (복사해서 사용)
    ├── inferences/
    │   ├── _template-vllm/.env.example
    │   └── _template-tei/.env.example
    ├── audio/
    │   └── _template-audio/.env.example
    └── networks/gateway/.env.example
```

## Quickstart (local)

```bash
# 1. 매니페스트 + 게이트웨이 env 생성
cp envs/_manifest.example.env envs/_manifest.local.env
cp envs/networks/gateway/.env.example envs/networks/gateway/.env.local
# → .env.local 의 GATEWAY_MASTER_KEY 채움 (예: openssl rand -hex 24)

# 2. 모델 컴포넌트 추가 (예: qwen3-8b)
cp -r deployment/inferences/_template-vllm     deployment/inferences/qwen3-8b
cp -r envs/inferences/_template-vllm           envs/inferences/qwen3-8b
cp     envs/inferences/qwen3-8b/.env.example   envs/inferences/qwen3-8b/.env.local
# → docker-compose.yml / gateway.yaml / .env.local 의 placeholder 를 채우고
# → envs/_manifest.local.env::INFERENCES 에 "qwen3-8b" 추가
# (오디오 컴포넌트는 _template-audio 를 같은 패턴으로 복사 + ::AUDIO 등재)

# 3. 부팅
make local-up

# 4. 확인
KEY=$(grep -E '^GATEWAY_MASTER_KEY=' envs/networks/gateway/.env.local | cut -d= -f2-)
curl -s -H "Authorization: Bearer $KEY" http://localhost:10080/v1/models | jq
```

- 클라이언트 API 스펙 (호출자 입장): `deployment/networks/gateway/API.md`
- 게이트웨이 아키텍처 / 라우팅 메커니즘 / 트러블슈팅: `deployment/networks/gateway/README.md`

## 네트워크 노출 정책 (default-safe + auth required)

게이트웨이는 default 로 **호스트 자신만 접근 가능** + **auth 필수**. 그 외 컨테이너 (vLLM/TEI/audio) 는 호스트에 포트 노출 자체를 하지 않습니다 — 게이트웨이를 통해서만 접근하는 단일 진입점 모델.

**허용되는 조합** (다른 조합은 boot 단계에서 차단)

| `GATEWAY_BIND` | `GATEWAY_MASTER_KEY` | 시나리오 | 안전 |
|---|---|---|---|
| `127.0.0.1` (default) | set | dev / 단일 호스트 / sandbox | ✅ |
| `0.0.0.0` | set | 외부 호출 (운영) | ✅ |
| (any) | unset 또는 empty | — | ❌ compose `:?` 가드가 boot 거부 |
| `0.0.0.0` | unset | 외부 노출 + no-auth (도용 위험) | ❌ 위와 동일 |

**왜?** no-auth 게이트웨이가 0.0.0.0 으로 떠 있으면 LAN/공용IP 노출 시 누구나 모델 호출 → 비용/리소스 도용. auth 를 항상 강제하면 그 시나리오가 코드 단계에서 불가능해집니다 (default-safe).

자세한 컨벤션과 불변 규칙은 `CLAUDE.md` 참고.
