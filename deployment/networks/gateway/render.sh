#!/usr/bin/env bash
# Build gateway routes.yaml by:
#   1. starting from gateway_routes.template.yaml (header + `backends:` 키)
#   2. reading `_manifest.<target>.env::INFERENCES` and `::AUDIO`
#   3. for each name in INFERENCES, appending
#      `deployment/inferences/<name>/gateway.yaml` (kind=inference fragment)
#   4. for each name in AUDIO, appending
#      `deployment/audio/<name>/gateway.yaml` (kind=audio fragment)
#
# 결과 파일 `routes.rendered.yaml` 은 gateway 컨테이너에 bind-mounted 됨.
# 매니페스트에 등재된 컴포넌트만 라우팅 → /v1/models 와 /audio/* 표면이
# 부팅 set 와 정확히 일치 (manifest = routing, 드리프트 원천 차단).
#
# Usage: render.sh <local|dev|prod>
set -euo pipefail

TARGET="${1:?usage: render.sh <local|dev|prod>}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MANIFEST="../../../envs/_manifest.${TARGET}.env"
TEMPLATE="./gateway_routes.template.yaml"
OUT="./routes.rendered.yaml"
INFERENCES_DIR="../../inferences"
AUDIO_DIR="../../audio"

if [ ! -f "$MANIFEST" ]; then
  echo "error: manifest not found: $(realpath "$MANIFEST" 2>/dev/null || echo "$MANIFEST")" >&2
  echo "hint:  cp ../../../envs/_manifest.example.env ../../../envs/_manifest.${TARGET}.env" >&2
  exit 1
fi
if [ ! -f "$TEMPLATE" ]; then
  echo "error: template not found: $TEMPLATE" >&2
  exit 1
fi

# shellcheck source=/dev/null
. "$MANIFEST"
INFERENCES="${INFERENCES:-}"
AUDIO="${AUDIO:-}"

cp "$TEMPLATE" "$OUT"

inf_count=0
inf_skipped=0
for name in $INFERENCES; do
  frag="${INFERENCES_DIR}/${name}/gateway.yaml"
  if [ ! -f "$frag" ]; then
    echo "::warning:: no gateway fragment at ${frag} — ${name} will NOT be routed (inference)" >&2
    inf_skipped=$((inf_skipped + 1))
    continue
  fi
  cat "$frag" >> "$OUT"
  inf_count=$((inf_count + 1))
done

audio_count=0
audio_skipped=0
for name in $AUDIO; do
  frag="${AUDIO_DIR}/${name}/gateway.yaml"
  if [ ! -f "$frag" ]; then
    echo "::warning:: no gateway fragment at ${frag} — ${name} will NOT be routed (audio)" >&2
    audio_skipped=$((audio_skipped + 1))
    continue
  fi
  cat "$frag" >> "$OUT"
  audio_count=$((audio_count + 1))
done

echo ">>> rendered ${OUT} (target=${TARGET}, inference=${inf_count}+skip${inf_skipped}, audio=${audio_count}+skip${audio_skipped})"
