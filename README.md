# spark-inference

DGX Spark(GB10/arm64) 단일 호스트에서 **vLLM + TEI** 모델을 띄우고
**LiteLLM** 게이트웨이로 OpenAI 호환 엔드포인트를 노출하는 인프라.

## 구조

```
spark-inference/
├── Makefile                        # make local-up / local-down / local-ps ...
├── deployment/                     # 배포 설정 — 어떻게 띄울지
│   ├── _run.sh                     # 매니페스트 기반 오케스트레이터
│   ├── inferences/
│   │   ├── _template-vllm/         # vLLM 컴포넌트 템플릿 (복사해서 사용)
│   │   └── _template-tei/          # TEI 컴포넌트 템플릿 (복사해서 사용)
│   └── networks/
│       └── litellm/                # OpenAI 호환 게이트웨이 (port 10080)
└── envs/                           # 환경변수 — 무엇을 띄울지 / 호스트별 값
    ├── _manifest.example.env       # 호스트별 부팅 매니페스트 (복사해서 사용)
    ├── inferences/
    │   ├── _template-vllm/.env.example
    │   └── _template-tei/.env.example
    └── networks/litellm/.env.example
```

## Quickstart (local)

```bash
# 1. 매니페스트 + env 파일 생성
cp envs/_manifest.example.env envs/_manifest.local.env
cp envs/networks/litellm/.env.example envs/networks/litellm/.env.local

# 2. 모델 컴포넌트 추가 (예: qwen3-8b)
cp -r deployment/inferences/_template-vllm     deployment/inferences/qwen3-8b
cp -r envs/inferences/_template-vllm           envs/inferences/qwen3-8b
cp     envs/inferences/qwen3-8b/.env.example   envs/inferences/qwen3-8b/.env.local
# → docker-compose.yml / litellm.yaml / .env.local 의 placeholder를 채우고
# → envs/_manifest.local.env::INFERENCES 에 "qwen3-8b" 추가

# 3. 부팅
make local-up

# 4. 확인
curl -s http://localhost:10080/v1/models | jq
```

## 네트워크 노출 정책 (default-safe)

LiteLLM 게이트웨이는 **호스트 자신만 접근 가능** 하도록 default-bind 됩니다.
그 외 컨테이너(vLLM/TEI)는 호스트에 포트 노출 자체를 하지 않습니다 — 게이트웨이를
통해서만 접근하는 단일 진입점 모델.

| 위치 | 기본값 | 의미 |
|---|---|---|
| `envs/networks/litellm/.env.<target>` 의 `SPARK_LITELLM_BIND` | `127.0.0.1` | loopback only — `localhost:10080` 만 도달 |
| 같은 변수 `0.0.0.0` 으로 변경 | (opt-in) | LAN/외부 노출. 방화벽/VPN/`LITELLM_MASTER_KEY` 중 하나 필수 |

**왜?** 게이트웨이는 default 로 no-auth 모드 (closed network 가정). 0.0.0.0 default 로
띄우면 LAN/공용IP 노출 시 누구든 모델 호출 가능 → 비용/리소스 도용 위험.
외부 노출은 명시적 opt-in 으로만.

자세한 컨벤션과 불변 규칙은 `CLAUDE.md` 참고.
