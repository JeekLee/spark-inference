# `_template-audio/` — Audio 컴포넌트 scaffolding

오디오 모델 (Madmom / BasicPitch / htdemucs 등) 을 FastAPI 로 감싸 LiteLLM pass-through 뒤에 붙이는 템플릿. `_` prefix 라 매니페스트에 등재 X (실제 부팅 대상 아님).

## 새 audio 컴포넌트 추가

```bash
# 1. 디렉토리 복사 (deployment 측)
cp -r deployment/audio/_template-audio deployment/audio/<name>

# 2. 디렉토리 복사 (envs 측)
cp -r envs/audio/_template-audio envs/audio/<name>

# 3. placeholder 치환 (`__NAME__`, `__NAME_UPPER__`)
cd deployment/audio/<name>
# docker-compose.yml, litellm.yaml, app/main.py 안의 placeholder 를
# 컴포넌트 이름으로 (예: madmom-chord, MADMOM_CHORD) 모두 치환.

# 4. 실제 모델 로직 작성
# - requirements.txt 에 모델 의존성 추가 (librosa, madmom, basic-pitch 등)
# - app/main.py 에 실제 처리 핸들러 구현 (placeholder 핸들러 교체)
# - 필요 시 docker-compose.yml 에 GPU 런타임 추가

# 5. 호스트 env 작성
cp envs/audio/<name>/.env.example envs/audio/<name>/.env.<target>
# 값 채움

# 6. 매니페스트 등재
# envs/_manifest.<target>.env::AUDIO 에 <name> 추가

# 7. 부팅
make <target>-up
```

## 게이트웨이 라우팅 패턴

`litellm.yaml` 의 한 entry 는 한 path 를 매핑:

```yaml
  - path: "/audio/<name>"
    target: "http://<name>:8000/<endpoint>"
```

클라이언트는 `https://<gateway>/audio/<name>` 으로 호출, master key 인증 자동.
한 컴포넌트에서 여러 endpoint 노출하려면 entry 를 추가하면 된다.

## CPU vs GPU

- **CPU 만**: `runtime: nvidia` 와 `NVIDIA_VISIBLE_DEVICES` 둘 다 빼면 됨 (템플릿 기본).
- **GPU 필요**: docker-compose.yml 의 주석 처리된 두 라인 활성. `__NAME_UPPER___GPU_IDS` 로 visible devices 지정.

## 인증

LiteLLM master key 인증이 pass-through 에도 자동 적용. 컴포넌트 자체에는 별도 auth 안 두는 게 default — 내부 docker network 만 노출되므로 두 layer 면 충분.
