# vLLM 컴포넌트 템플릿

신규 vLLM 모델 컴포넌트의 출발점.

## 사용법

```bash
NAME=qwen3-8b   # 컴포넌트 이름 (= 디렉토리명 = compose service명 = LiteLLM model_name)
NAME_UPPER=QWEN3_8B   # env var prefix용

# 1. deployment/envs 동시 복사
cp -r deployment/inferences/_template-vllm deployment/inferences/$NAME
cp -r envs/inferences/_template-vllm       envs/inferences/$NAME

# 2. placeholder 치환
sed -i "s/__NAME__/$NAME/g; s/__NAME_UPPER__/$NAME_UPPER/g" \
  deployment/inferences/$NAME/{docker-compose.yml,litellm.yaml} \
  envs/inferences/$NAME/.env.example

# 3. env 파일 생성 + 값 채우기
cp envs/inferences/$NAME/.env.example envs/inferences/$NAME/.env.local
# → ${NAME_UPPER}_IMAGE / ${NAME_UPPER}_MODEL_SUBDIR / ${NAME_UPPER}_GPU_IDS / ${NAME_UPPER}_TP_SIZE 등 수정

# 4. 매니페스트 등재 (= LiteLLM 라우팅 활성)
# envs/_manifest.local.env::INFERENCES 에 "$NAME" 추가

# 5. 부팅
make local-up
```

## 파일 구성

| 파일 | 역할 |
|---|---|
| `docker-compose.yml` | vLLM 컨테이너 정의. NVIDIA_VISIBLE_DEVICES + tensor-parallel 가변. |
| `litellm.yaml` | LiteLLM 라우팅 fragment (chat/instruct 모델). |
| `run.sh` | `./run.sh <target> <up\|down\|restart\|ps\|logs>` wrapper. |
