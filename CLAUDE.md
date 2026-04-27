# `spark-inference/` — 인프라 가이드

이 파일은 spark-inference 작업 시 따라야 할 **불변 규칙** 과 **문서 포인터** 만 담습니다.
사용법 / 명령 / 트러블슈팅 등 상세는 각 README 참조.

## 디렉토리 책임

| 경로 | 역할 |
|---|---|
| `deployment/` | 배포 설정 (compose, run.sh) — **어떻게 띄울지** |
| `envs/` | 환경변수 (`.env.<target>`, `_manifest.<target>.env`) — **무엇을 띄울지 / 호스트별 값** |

2영역 분리 원칙: 배포설정(`deployment/`) ↔ 환경변수(`envs/`).

## 불변 규칙

1. **`deployment/<category>/<name>/` ↔ `envs/<category>/<name>/` 1:1 매핑** — 같은 이름.
2. **카테고리는 운영 관심사로 나눔** — 기술 스택이 아님 (`inferences/` = GPU 자원, `networks/` = 라우팅).
3. **secret 은 git 금지** — `.env.example` / `_manifest.example.env` 만 추적, 나머지는 `envs/.gitignore` 로 차단. `.env.example` 에 실제 secret 기본값 박지 말 것.
4. **각 컴포넌트는 독립 docker-compose** — 모델 A 재기동이 모델 B 에 영향 X. 공유 external network `spark-inference-net` 에 join.
5. **`run.sh` wrapper 사용** — env 파일 경로를 외우게 하지 말 것. 인터페이스: `./run.sh <target> <up|down|restart|ps|logs>`.
6. **`_run.sh` 는 매니페스트 기반** — `_manifest.<target>.env` 의 `INFERENCES` / `NETWORKS` 에서 동적으로 읽음. `_run.sh` 자체에 컴포넌트 이름을 하드코딩하지 말 것.
7. **vLLM 백엔드는 `*_GPU_IDS` + `*_TP_SIZE` 로 가변** — 두 값의 GPU 개수가 일치해야 함. `NVIDIA_VISIBLE_DEVICES` 방식 (compose `device_ids` 는 길이 가변 불가).
8. **gateway 라우팅은 컴포넌트 곁의 fragment** — 라우팅되는 모델마다 `deployment/inferences/<name>/litellm.yaml` 작성. `litellm_config.yaml` 을 손으로 편집하지 말 것. `networks/litellm/render.sh` 가 매니페스트(`_manifest.<target>.env::INFERENCES`) 에 등재된 fragment 만 concat 해서 `litellm_config.rendered.yaml` 을 만들고 compose 가 그걸 마운트함. **매니페스트 = gateway 라우팅** (드리프트 원천 차단).
9. **`_` 로 시작하는 디렉토리는 scaffolding** — 실제 부팅 대상 아님 (`_template-vllm/`, `_template-tei/`). 매니페스트에 등재하지 말 것.
10. **이미지 우선순위: NGC > OSS** — 같은 모델/버전이면 NGC(`nvcr.io/nvidia/...`) 우선. arm64/Blackwell 호환성이 OSS 보다 안정적. OSS 가 필요하면 `.env` 의 `*_IMAGE` 변수만 갈아끼울 것.
11. **호스트 노출은 default-safe** — LiteLLM gateway 의 `ports:` 호스트 IP 부분은 `${SPARK_LITELLM_BIND:-127.0.0.1}` 로 변수화. **default = loopback 만**. no-auth 게이트웨이를 `0.0.0.0` 으로 default-bind 하면 LAN/공용IP 노출 시 누구든 모델 호출 가능 (비용/리소스 도용). 외부 노출이 필요하면 `.env.<target>` 에 `SPARK_LITELLM_BIND=0.0.0.0` 을 명시적으로 설정 + 방화벽/VPN/인증 중 하나로 신뢰 경계 확보. vLLM/TEI 백엔드 컨테이너에는 `ports:` 자체를 두지 말 것 — 게이트웨이 통해서만 접근.

## 새 컴포넌트 추가 체크리스트

1. 템플릿 복사:
   - vLLM 모델: `cp -r deployment/inferences/_template-vllm deployment/inferences/<name>` + `cp -r envs/inferences/_template-vllm envs/inferences/<name>`
   - TEI 모델: `cp -r deployment/inferences/_template-tei deployment/inferences/<name>` + `cp -r envs/inferences/_template-tei envs/inferences/<name>`
2. `<name>` placeholder 치환 (`docker-compose.yml`, `litellm.yaml`, `.env.example` 안의 `__NAME__` / `__NAME_UPPER__`)
3. `envs/<category>/<name>/.env.example` → `.env.<target>` 복사 후 값 채우기
4. `envs/_manifest.<target>.env::INFERENCES` 에 `<name>` 추가 → 자동으로 LiteLLM 라우팅도 활성
5. 부팅: `make <target>-up` (또는 `cd deployment/inferences/<name> && ./run.sh <target> up`)

> `_run.sh` / `Makefile` 은 수정 불필요 — 매니페스트 기반 자동 발견.

## 문서 포인터

- **`README.md`** — Quickstart
- **`deployment/networks/litellm/README.md`** — Gateway 사용법 / 클라이언트 예제
