# TEI 컴포넌트 템플릿

신규 임베딩 / 리랭커 모델 컴포넌트의 출발점. (Hugging Face TEI 기반)

## 사용법

```bash
NAME=bge-m3
NAME_UPPER=BGE_M3

cp -r deployment/inferences/_template-tei deployment/inferences/$NAME
cp -r envs/inferences/_template-tei       envs/inferences/$NAME

sed -i "s/__NAME__/$NAME/g; s/__NAME_UPPER__/$NAME_UPPER/g" \
  deployment/inferences/$NAME/{docker-compose.yml,litellm.yaml} \
  envs/inferences/$NAME/.env.example

cp envs/inferences/$NAME/.env.example envs/inferences/$NAME/.env.local
# → ${NAME_UPPER}_IMAGE / ${NAME_UPPER}_MODEL_SUBDIR / ${NAME_UPPER}_GPU 등 수정

# envs/_manifest.local.env::INFERENCES 에 "$NAME" 추가
make local-up
```

## 이미지 주의사항

GB10 (Blackwell sm_100/120 + arm64) 호환 TEI 태그가 모든 버전에 존재하진
않습니다. tag 페이지에서 arm64 manifest 와 GPU compute capability 를 확인하고,
없으면 OSS 빌드(또는 CPU-only 임시 운용)를 고려하세요.

- 태그 목록: <https://github.com/huggingface/text-embeddings-inference/pkgs/container/text-embeddings-inference>
- 소스 빌드: <https://github.com/huggingface/text-embeddings-inference#docker-build>

## 파일 구성

| 파일 | 역할 |
|---|---|
| `docker-compose.yml` | TEI 컨테이너. 단일 GPU 슬롯 (compose `device_ids`). |
| `litellm.yaml` | LiteLLM 라우팅 fragment (`drop_params: true` 필수). |
| `run.sh` | `./run.sh <target> <up\|down\|restart\|ps\|logs>` wrapper. |
