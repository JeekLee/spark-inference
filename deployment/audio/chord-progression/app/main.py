"""audio/chord-progression — chord progression recommender via qwen3-8b.

Endpoint: POST /generate
  Body: application/json
    {
      "seed_chords": "Am CM Dm E7",   // optional — predict next chords from these
      "nb_chords": 8,                  // number of NEW chords to recommend
      "temperature": 0.7,              // sampling temperature
      "seed": null                     // int for reproducibility (best-effort, vLLM)
    }
  Response:
    {
      "seed_chords": ["Am", "CM", "Dm", "E7"],
      "predicted_chords": ["Am", "FM", "G7", "CM", "Am", "Dm", "G7", "CM"],
      "raw": "Am FM G7 CM Am Dm G7 CM"   // upstream content before parsing (debug)
    }

내부 동작: 같은 docker network 의 qwen3-8b vLLM 백엔드(OpenAI-compat) 를
chat/completions 로 호출. system prompt 로 chord theory 컨벤션 + 출력
포맷(공백 구분 코드 심볼) 강제. response 를 chord 토큰 리스트로 파싱.

게이트웨이(`networks/gateway`) 가 인증 + 외부 노출 담당. 컴포넌트 자체는
internal docker network 만 노출.
"""
from __future__ import annotations

import logging
import os
import re

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=os.environ.get("CHORD_PROGRESSION_LOG_LEVEL", "INFO"))
log = logging.getLogger("chord-progression")

UPSTREAM_URL = os.environ.get("CHORD_PROGRESSION_UPSTREAM_URL", "http://qwen3-8b:8000")
UPSTREAM_MODEL = os.environ.get("CHORD_PROGRESSION_UPSTREAM_MODEL", "qwen3-8b")
UPSTREAM_TIMEOUT = float(os.environ.get("CHORD_PROGRESSION_UPSTREAM_TIMEOUT", "30"))

# Pop-format chord regex. Used to filter LLM output → chord tokens only.
# 허용: 루트(A-G) + accidental(#/b)? + quality(M, m, 7, m7, M7, m7b5, dim, o, aug, sus2, sus4)? + bass(/X)?
_CHORD_RE = re.compile(
    r"^[A-G][#b]?(?:M7|m7b5|m7|M|m|7|dim|aug|o|sus2|sus4)?(?:/[A-G][#b]?)?$"
)

SYSTEM_PROMPT = (
    "You are a music theory expert that recommends chord progressions.\n"
    "Output ONLY chord symbols on a single line, space-separated. No commentary, "
    "no numbering, no markdown.\n"
    "Use standard pop chord notation:\n"
    "  - Root: A, B, C, D, E, F, G with optional # or b accidental\n"
    "  - Quality: M (major), m (minor), 7, M7, m7, m7b5, dim, aug, sus2, sus4\n"
    "  - Inversion: /Root  (e.g. CM/E)\n"
    "Examples: Am, CM, G7, Dm7, F#m, Bb, CM/E\n"
    "Do not invent unusual chords. Stick to common functional harmony."
)

FEW_SHOT_EXAMPLES = [
    {
        "user": "Continue this chord progression with 4 more chords:\nAm CM Dm E7",
        "assistant": "Am Dm G7 CM",
    },
    {
        "user": "Continue this chord progression with 4 more chords:\nCM G7",
        "assistant": "Am Em FM CM",
    },
    {
        "user": "Generate a chord progression of 4 chords.",
        "assistant": "CM Am FM G7",
    },
]

app = FastAPI(title="chord-progression — spark-inference audio service")
_client = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT)


class GenerateRequest(BaseModel):
    seed_chords: str | None = Field(
        default=None,
        description='Space-separated chord symbols, e.g. "Am CM Dm E7".',
    )
    nb_chords: int = Field(default=8, ge=1, le=64)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    seed: int | None = None


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "service": "chord-progression",
        "upstream": UPSTREAM_URL,
        "model": UPSTREAM_MODEL,
    }


@app.post("/generate")
async def generate(req: GenerateRequest) -> dict[str, object]:
    seed_tokens = _normalize_seed(req.seed_chords)

    if seed_tokens:
        user_msg = (
            f"Continue this chord progression with {req.nb_chords} more chords:\n"
            + " ".join(seed_tokens)
        )
    else:
        user_msg = f"Generate a chord progression of {req.nb_chords} chords."

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for ex in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": ex["user"]})
        messages.append({"role": "assistant", "content": ex["assistant"]})
    messages.append({"role": "user", "content": user_msg})

    payload: dict[str, object] = {
        "model": UPSTREAM_MODEL,
        "messages": messages,
        "temperature": req.temperature,
        "max_tokens": max(64, req.nb_chords * 8),
        "stop": ["\n"],
        # Qwen3 의 thinking 모드는 content 를 비우고 모든 토큰을 reasoning 에 쓰므로 비활성.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if req.seed is not None:
        payload["seed"] = req.seed

    try:
        resp = await _client.post(
            f"{UPSTREAM_URL}/v1/chat/completions",
            json=payload,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.exception("upstream call failed")
        raise HTTPException(status_code=502, detail=f"upstream call failed: {exc}")

    body = resp.json()
    try:
        raw = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        log.exception("unexpected upstream response: %s", body)
        raise HTTPException(
            status_code=502, detail=f"unexpected upstream response shape: {exc}"
        )

    predicted = _parse_chords(raw)[: req.nb_chords]

    return {
        "seed_chords": seed_tokens,
        "predicted_chords": predicted,
        "raw": raw,
    }


def _normalize_seed(seed: str | None) -> list[str]:
    if not seed:
        return []
    return [tok for tok in seed.strip().split() if tok]


def _parse_chords(raw: str) -> list[str]:
    """LLM 출력에서 chord 토큰만 추출. 다양한 구분자 허용 후 regex 필터."""
    candidates = re.split(r"[\s,;|\-]+", raw.strip())
    return [tok for tok in candidates if tok and _CHORD_RE.match(tok)]
