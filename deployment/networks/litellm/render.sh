#!/usr/bin/env bash
# Build litellm_config.rendered.yaml by:
#   1. starting from litellm_config.template.yaml (header — general/litellm settings)
#   2. reading `_manifest.<target>.env::INFERENCES` and `::AUDIO`
#   3. for each INFERENCES entry, appending
#      `deployment/inferences/<name>/litellm.yaml` under `model_list:`
#   4. for each AUDIO entry, appending
#      `deployment/audio/<name>/litellm.yaml` under `pass_through_endpoints:`
#
# The rendered file is bind-mounted into the litellm container. Components
# not listed in the manifest are NOT routed → /v1/models and the pass-through
# surface match the boot set exactly (manifest = gateway routing, no drift).
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

# ── audio components → pass_through_endpoints (header emitted only if ≥1 valid) ──
audio_count=0
audio_skipped=0
audio_buffer="$(mktemp)"
trap 'rm -f "$audio_buffer"' EXIT
for name in $AUDIO; do
  frag="${AUDIO_DIR}/${name}/litellm.yaml"
  if [ ! -f "$frag" ]; then
    echo "::warning:: no litellm fragment at ${frag} — ${name} will NOT be routed (audio)" >&2
    audio_skipped=$((audio_skipped + 1))
    continue
  fi
  cat "$frag" >> "$audio_buffer"
  audio_count=$((audio_count + 1))
done
if [ "$audio_count" -gt 0 ]; then
  echo "" >> "$OUT"
  echo "pass_through_endpoints:" >> "$OUT"
  cat "$audio_buffer" >> "$OUT"
fi

echo ">>> rendered ${OUT} (target=${TARGET}, chat=${chat_count}+skip${chat_skipped}, audio=${audio_count}+skip${audio_skipped})"
