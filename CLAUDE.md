# `spark-inference/` — 인프라 가이드

이 파일은 spark-inference 작업 시 따라야 할 **불변 규칙** 과 **문서 포인터** 만 담습니다.
사용법 / 명령 / 트러블슈팅 등 상세는 각 README 참조.

## 디렉토리 책임

| 경로 | 역할 |
|---|---|
| `deployment/` | 배포 설정 (compose, run.sh) — **어떻게 띄울지** |
| `envs/` | 환경변수 (`.env.<target>`, `_manifest.<target>.env`) — **무엇을 띄울지 / 호스트별 값** |
| `benchmarks/` | 게이트웨이 너머 모델 비교 평가 셋 (벤치 스크립트 + 프롬프트) |

2영역 분리 원칙: 배포설정(`deployment/`) ↔ 환경변수(`envs/`).

`deployment/` 하위 카테고리 (운영 관심사 기준):
- `inferences/` — vLLM/TEI 등 GPU LLM/embedding 서빙 (chat/embed `kind=inference`)
- `audio/` — FastAPI 기반 오디오 모델 서빙 (multipart/binary, `kind=audio`)
- `networks/` — 게이트웨이 / 라우터 (`gateway` — 자체 FastAPI + httpx 프록시)

## 불변 규칙

1. **`deployment/<category>/<name>/` ↔ `envs/<category>/<name>/` 1:1 매핑** — 같은 이름.
2. **카테고리는 운영 관심사로 나눔** — 기술 스택이 아님 (`inferences/` = GPU 자원, `networks/` = 라우팅).
3. **secret 은 git 금지** — `.env.example` / `_manifest.example.env` 만 추적, 나머지는 `envs/.gitignore` 로 차단. `.env.example` 에 실제 secret 기본값 박지 말 것.
4. **각 컴포넌트는 독립 docker-compose** — 모델 A 재기동이 모델 B 에 영향 X. 공유 external network `spark-inference-net` 에 join.
5. **`run.sh` wrapper 사용** — env 파일 경로를 외우게 하지 말 것. 인터페이스: `./run.sh <target> <up|down|restart|ps|logs>`.
6. **`_run.sh` 는 매니페스트 기반** — `_manifest.<target>.env` 의 `INFERENCES` / `AUDIO` / `NETWORKS` 에서 동적으로 읽음. `_run.sh` 자체에 컴포넌트 이름을 하드코딩하지 말 것.
7. **vLLM 백엔드는 `*_GPU_IDS` + `*_TP_SIZE` 로 가변** — 두 값의 GPU 개수가 일치해야 함. `NVIDIA_VISIBLE_DEVICES` 방식 (compose `device_ids` 는 길이 가변 불가).
8. **gateway 라우팅은 컴포넌트 곁의 fragment** — 라우팅되는 컴포넌트마다 `gateway.yaml` fragment 작성. `routes.rendered.yaml` 을 손으로 편집하지 말 것.
   - chat/embed: `deployment/inferences/<name>/gateway.yaml` → `kind: inference` (model + url)
   - audio: `deployment/audio/<name>/gateway.yaml` → `kind: audio` (path + target)
   - `networks/gateway/render.sh` 가 매니페스트(`_manifest.<target>.env::INFERENCES` + `::AUDIO`) 에 등재된 fragment 만 concat. **매니페스트 = gateway 라우팅** (드리프트 원천 차단).
9. **`_` 로 시작하는 디렉토리는 scaffolding** — 실제 부팅 대상 아님 (`_template-vllm/`, `_template-tei/`, `_template-audio/`). 매니페스트에 등재하지 말 것.
10. **이미지 선택은 호스트 컨텍스트 + 명시 핀** — `vllm/vllm-openai` (OSS Docker Hub) 는 인증 불필요 + multi-arch manifest 자동 매칭. NGC (`nvcr.io/nvidia/vllm`) 는 NVIDIA 가 직접 빌드/검증해 arm64+Blackwell 같은 신규 조합에서 안정성 ↑ (단 NGC 계정 필요). 한 호스트는 한 source 로 통일하고, 부팅 실패(PTX/SASS 에러 등) 시 다른 source 로 폴백. **이미지 태그는 항상 명시 핀** (`v0.19.1` 등) — `:latest` 는 커밋 X.
11. **호스트 노출은 default-safe + auth 필수, 게이트웨이 한 곳만** — invariant 가 함께 강제됨.
    - **bind**: gateway 의 `ports:` 호스트 IP 부분은 `${GATEWAY_BIND:-127.0.0.1}` 로 변수화. default = loopback 만.
    - **auth**: `GATEWAY_MASTER_KEY` 는 compose 의 `:?` 가드 + 게이트웨이 startup 의 RuntimeError 양쪽으로 **항상 필수** — unset/empty 면 boot 거부. 클라이언트는 `Authorization: Bearer <key>` 동봉.
    - 허용 조합: `127.0.0.1+key` (dev/sandbox), `0.0.0.0+key` (외부 호출). `0.0.0.0+no-key` 는 compose 단계에서 차단.
    - **백엔드 컨테이너에는 `ports:` 두지 말 것** — vLLM/TEI/audio 모두 게이트웨이 통해서만 접근. auth/로깅/메트릭이 게이트웨이 한 곳에 일원화됨.

## 새 컴포넌트 추가 체크리스트

1. 템플릿 복사:
   - vLLM 모델: `cp -r deployment/inferences/_template-vllm deployment/inferences/<name>` + `cp -r envs/inferences/_template-vllm envs/inferences/<name>`
   - TEI 모델: `cp -r deployment/inferences/_template-tei deployment/inferences/<name>` + `cp -r envs/inferences/_template-tei envs/inferences/<name>`
   - Audio 모델: `cp -r deployment/audio/_template-audio deployment/audio/<name>` + `cp -r envs/audio/_template-audio envs/audio/<name>`
2. `<name>` placeholder 치환 (`docker-compose.yml`, `gateway.yaml`, `.env.example`, `app/main.py` 안의 `__NAME__` / `__NAME_UPPER__`)
3. `envs/<category>/<name>/.env.example` → `.env.<target>` 복사 후 값 채우기
4. 매니페스트 등재 → 자동으로 게이트웨이 라우팅도 활성
   - vLLM/TEI: `envs/_manifest.<target>.env::INFERENCES` 에 `<name>` 추가
   - Audio: `envs/_manifest.<target>.env::AUDIO` 에 `<name>` 추가
5. 부팅: `make <target>-up` (또는 `cd deployment/<category>/<name> && ./run.sh <target> up`)

> `_run.sh` / `Makefile` 은 수정 불필요 — 매니페스트 기반 자동 발견.

## 문서 포인터

- **`README.md`** — Quickstart
- **`deployment/networks/gateway/README.md`** — Gateway 사용법 / 라우팅 모델 / 클라이언트 예제
