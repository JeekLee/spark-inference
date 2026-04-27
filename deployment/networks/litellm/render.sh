#!/usr/bin/env bash
# Build litellm_config.rendered.yaml by:
#   1. starting from litellm_config.template.yaml
#   2. reading `_manifest.<target>.env::INFERENCES`
#   3. appending each listed component's
#      `deployment/inferences/<name>/litellm.yaml` fragment
#
# The rendered file is bind-mounted into the litellm container. Models not
# listed in the manifest are NOT routed → /v1/models matches the boot set.
#
# Usage: render.sh <local|dev|prod>
set -euo pipefail

TARGET="${1:?usage: render.sh <local|dev|prod>}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MANIFEST="../../../envs/_manifest.${TARGET}.env"
TEMPLATE="./litellm_config.template.yaml"
OUT="./litellm_config.rendered.yaml"
FRAGMENTS_DIR="../../inferences"

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

count=0
skipped=0
for name in $INFERENCES; do
  frag="${FRAGMENTS_DIR}/${name}/litellm.yaml"
  if [ ! -f "$frag" ]; then
    echo "::warning:: no litellm fragment at ${frag} — ${name} will NOT be routed" >&2
    skipped=$((skipped + 1))
    continue
  fi
  echo "" >> "$OUT"
  cat "$frag" >> "$OUT"
  count=$((count + 1))
done

echo ">>> rendered ${OUT} (target=${TARGET}, routed=${count}, skipped=${skipped})"
