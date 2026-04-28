# `deployment/` — 배포 설정

각 컴포넌트는 **독립 docker-compose** 로 정의되며, 공유 외부 네트워크
`spark-inference-net` 에 join 합니다. 컴포넌트 부팅 대상은 호스트별
매니페스트(`envs/_manifest.<target>.env`)로 결정됩니다.

## 명령

```bash
# 전체 스택
make local-up        # = ./deployment/_run.sh local up
make local-down
make local-ps
make local-logs
make local-logs-c C=gateway   # 단일 컴포넌트 로그

# 단일 컴포넌트만
cd deployment/inferences/<name>  && ./run.sh local up
cd deployment/audio/<name>       && ./run.sh local up
cd deployment/networks/gateway   && ./run.sh local up
```

## 컴포넌트 카테고리

| 카테고리 | 역할 | 부팅 순서 |
|---|---|---|
| `inferences/` | vLLM/TEI 등 OpenAI-compat 모델 서빙 (chat/embed) | 1 |
| `audio/`      | FastAPI 기반 오디오 모델 (multipart/binary) | 2 |
| `networks/`   | spark-gateway (단일 진입점, port 10080) | 3 (마지막) |

부팅 순서는 `_run.sh` 가 강제. 종료는 역순.

## 새 컴포넌트 추가

`CLAUDE.md` 의 "새 컴포넌트 추가 체크리스트" 참고.

요약: 카테고리별 템플릿 디렉토리 (`_template-vllm` / `_template-tei` / `_template-audio`) 복사 → placeholder 치환 → `envs/_manifest.<target>.env::{INFERENCES,AUDIO}` 에 이름 추가. 끝. 게이트웨이 라우팅은 `networks/gateway/render.sh` 가 매니페스트 + 컴포넌트의 `gateway.yaml` fragment 로 자동 생성.
