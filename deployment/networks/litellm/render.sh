#!/usr/bin/env bash
# Build litellm_config.rendered.yaml by:
#   1. starting from litellm_config.template.yaml (header — general/litellm settings)
#   2. reading `_manifest.<target>.env::INFERENCES`
#   3. for each INFERENCES entry, appending
#      `deployment/inferences/<name>/litellm.yaml` under `model_list:`
#
# Audio components are NOT routed via LiteLLM — see CLAUDE.md invariant 11.
# LiteLLM v1.82.3 의 pass_through_endpoints 가 multipart/form-data 와
# 호환되지 않아(custom_body 파라미터로 인한 FastAPI Body 검증 실패),
# audio 컴포넌트는 자체 host port + Bearer auth 로 직접 노출한다.
#
# The rendered file is bind-mounted into the litellm container. Components
# not listed in the manifest are NOT routed → /v1/models matches the boot
# set exactly (manifest = gateway routing, no drift).
#
# Usage: render.sh <local|dev|prod>
set -euo pipefail

TARGET="${1:?usage: render.sh <local|dev|prod>}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MANIFEST="../../../envs/_manifest.${TARGET}.env"
TEMPLATE="./litellm_config.template.yaml"
OUT="./litellm_config.rendered.yaml"
INFERENCES_DIR="../../inferences"

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

cp "$TEMPLATE" "$OUT"

# ── chat / embedding models → model_list (already opened by template) ──
chat_count=0
chat_skipped=0
for name in $INFERENCES; do
  frag="${INFERENCES_DIR}/${name}/litellm.yaml"
  if [ ! -f "$frag" ]; then
    echo "::warning:: no litellm fragment at ${frag} — ${name} will NOT be routed (chat)" >&2
    chat_skipped=$((chat_skipped + 1))
    continue
  fi
  echo "" >> "$OUT"
  cat "$frag" >> "$OUT"
  chat_count=$((chat_count + 1))
done

echo ">>> rendered ${OUT} (target=${TARGET}, chat=${chat_count}+skip${chat_skipped})"
