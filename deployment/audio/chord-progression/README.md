# `audio/musiclang-chord/` — Chord Progression Generation

[MusicLang text-chord-predictor](https://huggingface.co/musiclang/text-chord-predictor) (6.82M params, GPT-2, ~27MB) 를 FastAPI 로 감싸 spark-gateway 뒤에 노출.

**용도**: 코드 진행(chord progression) 추천. 시드 코드를 받아 다음 코드를 예측, 또는 시드 없이 처음부터 생성. `madmom-chord` 가 코드 *인식* (오디오 → 코드) 인 반면, 이 컴포넌트는 코드 *생성* (시드 → 진행).

**왜 chord-v2-4k 가 아니라 text-chord-predictor 인가**: chord-v2-4k 는 musiclang DSL 객체를 prompt 로 받아 musiclang_predict 라는 추가 패키지 의존이 필요. text-chord-predictor 는 표준 chord 심볼 텍스트("START Am Dm G7") 입출력 + 순수 HF transformers — 의존성 단순, 클라이언트 API 도 직관적.

## 자원

- **CPU only** — 6.82M 파라미터라 GPU 불필요
- 메모리: ~500MB
- 모델 가중치는 빌드 단계에서 prefetch (`HF_HOME=/app/.cache/huggingface`)

## 게이트웨이 라우팅

```yaml
- kind: audio
  path: /v1/audio/chord-progression
  target: http://musiclang-chord:8000/generate
```

→ 클라이언트는 `POST {gateway}/v1/audio/chord-progression` 으로 호출.

## 호출 예

```bash
curl -X POST https://${GATEWAY}/v1/audio/chord-progression \
  -H "Authorization: Bearer ${GATEWAY_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "seed_chords": "Am CM Dm E7",
    "nb_chords": 8,
    "temperature": 1.0,
    "seed": 42
  }'
```

응답:
```json
{
  "seed_chords": ["Am", "CM", "Dm", "E7"],
  "predicted_chords": ["Am", "FM", "G7", "CM", "Am", "Dm", "G7", "CM"]
}
```

## 입력 제약

- 지원 chord quality: `M, m, 7, M7, m7, m7b5, dim, o, aug`
- 인버전: `CM/E` (베이스는 코드 구성음에 한함)
- vocab 에 없는 코드 (`C#M`) 는 enharmonic equivalent (`DbM`) 로 호출자가 정규화 후 전달
- 모델은 chord 정확도가 우선이며 harmonic rhythm (각 코드가 몇 박자) 은 모델링 X
- "코드 진행이 정확히 시드대로 보존되는 것은 보장 X" — 생성 모델 특성

## 재현성

`seed` 파라미터에 정수 전달 시 `torch.manual_seed` 로 결정적 출력. null/생략 시 매 호출마다 다른 결과.
