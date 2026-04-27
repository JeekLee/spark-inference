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
LITELLM_MASTER_KEY=sk-spark-...  # REQUIRED — generate with the snippet below
```

## Auth & 네트워크 노출

게이트웨이는 default 로 **localhost-only + auth required**. 둘 중 어느 한쪽도
끄지 않습니다 — compose 의 `:?` 가드가 `LITELLM_MASTER_KEY` 미설정 시 boot
자체를 거부합니다.

| `SPARK_LITELLM_BIND` | `LITELLM_MASTER_KEY` | 결과 |
|---|---|---|
| `127.0.0.1` (default) | set | ✅ auth + host-only (dev) |
| `0.0.0.0` | set | ✅ auth + 외부 호출 (운영) |
| (any) | unset/empty | ❌ compose 가 boot 거부 |
| `0.0.0.0` | unset | ❌ 위와 동일 (= 위험 조합 차단) |

### 첫 부팅 절차

```bash
cd envs/networks/litellm
cp .env.example .env.local

# master key 생성 + .env.local 에 적용
KEY=$(openssl rand -hex 24 | xargs printf 'sk-spark-%s\n')
sed -i "s|^#LITELLM_MASTER_KEY=$|LITELLM_MASTER_KEY=$KEY|" .env.local
echo "saved: $KEY"   # 클라이언트에 알려줄 값

cd ../../../deployment/networks/litellm
./run.sh local up
```

### 외부 호출 활성화

`.env.<target>` 에서 `SPARK_LITELLM_BIND=127.0.0.1` → `0.0.0.0` 변경 후
`./run.sh <target> restart`. (master key 는 이미 있으니 추가 작업 불필요.)

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

`.env.<target>` 의 `LITELLM_MASTER_KEY` 값을 Bearer token 으로 동봉.

```bash
KEY=sk-spark-...   # = LITELLM_MASTER_KEY
curl -sS http://localhost:10080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $KEY" \
  -d '{"model":"<모델이름>","messages":[{"role":"user","content":"hello"}]}'
```

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:10080/v1",
    api_key="sk-spark-...",   # = LITELLM_MASTER_KEY
)
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
