# LiteLLM gateway

OpenAI 호환 LLM/임베딩 게이트웨이. 단일 호스트 포트
(`${SPARK_LITELLM_PORT:-10080}`) 로 `deployment/inferences/` 의 모든 모델을
프론팅합니다.

## Depends on

- 외부 docker 네트워크 `spark-inference-net` (`deployment/_run.sh up` 이 자동 생성)
- `deployment/inferences/<name>/` 에 등록된 백엔드. 매니페스트
  (`envs/_manifest.<target>.env::INFERENCES`) 에 등재된 컴포넌트만 라우팅됨.

## 환경 파일

`envs/networks/litellm/.env.<target>`:

```
SPARK_LITELLM_BIND=127.0.0.1     # optional, default 127.0.0.1 (host-only)
SPARK_LITELLM_PORT=10080         # optional, default 10080
LITELLM_IMAGE_TAG=main-stable    # optional, default main-stable
LITELLM_LOG=INFO                 # optional, default INFO
```

## Auth & 네트워크 노출

**No-auth 모드** + **localhost-only bind** 가 default. compose 가 의도적으로
`LITELLM_MASTER_KEY` 를 전달하지 않으며 (빈 값을 줘도 litellm 이 인증을 강제),
호스트 노출은 `127.0.0.1:10080` 으로 제한됩니다.

이 둘이 함께여야 안전합니다:

| 인증 | bind | 결과 |
|---|---|---|
| no-auth | `127.0.0.1` | ✅ 안전 (default) — 호스트 자신만 도달 |
| no-auth | `0.0.0.0`   | 🚨 위험 — 누구나 모델 호출 가능 |
| auth 활성 | `0.0.0.0` | OK (TLS + 강한 키 가정) |

외부 노출이 필요하면:
1. `SPARK_LITELLM_BIND=0.0.0.0` 으로 바꾸기 **전에** docker-compose.yml 에
   `LITELLM_MASTER_KEY` env 를 넣어 auth 활성화 — 또는 방화벽/VPN으로 신뢰
   네트워크에만 노출되는지 확인.
2. 값 변경 후 `./run.sh <target> restart`.

## Start / stop

```bash
# 이 디렉토리에서 (단독)
./run.sh local up
./run.sh local down
./run.sh local restart
./run.sh local ps
./run.sh local logs

# 또는 루트에서 (전체 스택)
make local-up
```

`up` / `restart` 시 `render.sh` 가 자동 실행되어 매니페스트 기반으로
`litellm_config.rendered.yaml` 을 다시 만듭니다.

## 클라이언트 사용

```bash
curl -sS http://localhost:10080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"<모델이름>","messages":[{"role":"user","content":"hello"}]}'
```

```python
# api_key 는 SDK가 요구하지만 게이트웨이는 무시합니다 (no-auth).
from openai import OpenAI

client = OpenAI(base_url="http://localhost:10080/v1", api_key="not-used")
client.chat.completions.create(
    model="<모델이름>",
    messages=[{"role": "user", "content": "hello"}],
)
```

## Health

```bash
curl -sS http://localhost:10080/health/liveliness
curl -sS http://localhost:10080/v1/models | jq
```
