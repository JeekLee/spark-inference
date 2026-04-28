# `_template-audio/` — Audio 컴포넌트 scaffolding

오디오 모델 (Madmom / BasicPitch / htdemucs 등) 을 FastAPI 로 감싸 호스트 포트로 직접 노출하는 템플릿. `_` prefix 라 매니페스트에 등재 X (실제 부팅 대상 아님).

## 왜 LiteLLM 게이트웨이를 안 거치나?

LiteLLM v1.82.3 의 `pass_through_endpoints` 라우트 시그니처가 `custom_body: Optional[dict]` 를 가지면서 FastAPI 가 multipart body 를 dict 로 검증 시도 → 422/500. 오디오 업로드는 multipart 가 표준이므로 게이트웨이 통합을 포기하고 컴포넌트별로 직접 노출 + 자체 Bearer auth 로 우회. CLAUDE.md invariant 11 / 12 참조.

## 새 audio 컴포넌트 추가

```bash
# 1. 디렉토리 복사 (deployment 측)
cp -r deployment/audio/_template-audio deployment/audio/<name>

# 2. 디렉토리 복사 (envs 측)
cp -r envs/audio/_template-audio envs/audio/<name>

# 3. placeholder 치환 (`__NAME__`, `__NAME_UPPER__`)
cd deployment/audio/<name>
# docker-compose.yml, app/main.py 안의 placeholder 를 컴포넌트 이름으로
# (예: madmom-chord, MADMOM_CHORD) 모두 치환. envs 의 .env.example 도 같이.

# 4. 실제 모델 로직 작성
# - requirements.txt 에 모델 의존성 추가 (librosa, madmom, basic-pitch 등)
# - app/main.py 에 실제 처리 핸들러 구현 (placeholder 핸들러 교체)
#   `dependencies=[Depends(require_bearer)]` 는 보존
# - 필요 시 docker-compose.yml 에 GPU 런타임 추가

# 5. 호스트 env 작성
cp envs/audio/<name>/.env.example envs/audio/<name>/.env.<target>
# - <NAME>_HOST_PORT 를 충돌 없는 값으로 (예: 10081, 10082, ...)
# - AUDIO_MASTER_KEY 를 LITELLM_MASTER_KEY 와 동일 값으로 세팅 (단일 키 UX)

# 6. 매니페스트 등재
# envs/_manifest.<target>.env::AUDIO 에 <name> 추가

# 7. 부팅
make <target>-up
```

## 노출 포트 / 라우팅 패턴

각 audio 컴포넌트는 자체 host port 로 노출:

```bash
KEY=<AUDIO_MASTER_KEY 와 같은 값>
curl -X POST -H "Authorization: Bearer $KEY" \
     -F "audio=@clip.wav" \
     http://127.0.0.1:<HOST_PORT>/<endpoint>
```

LiteLLM (chat/embed) 과 동일한 Bearer auth 패턴이지만 별도 process — 인증 키만 통일하면 클라이언트는 한 가지 키로 양쪽 다 호출 가능.

## CPU vs GPU

- **CPU 만**: `runtime: nvidia` 와 `NVIDIA_VISIBLE_DEVICES` 둘 다 빼면 됨 (템플릿 기본).
- **GPU 필요**: docker-compose.yml 의 주석 처리된 두 라인 활성. `__NAME_UPPER___GPU_IDS` 로 visible devices 지정.

## 인증

`AUDIO_MASTER_KEY` 환경변수가 비어있으면 startup 거부 (`:?` 가드 + Python 측 RuntimeError 양쪽). FastAPI dependency `require_bearer` 가 모든 비-health 엔드포인트 앞에 붙어 Bearer 검증.
