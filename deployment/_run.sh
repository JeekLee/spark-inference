#!/usr/bin/env bash
# spark-inference/deployment/_run.sh
#
# Orchestrate the spark-inference stack. Reads the per-target manifest at
# envs/_manifest.<target>.env to decide which components to boot — different
# hosts can run different subsets without editing any compose file.
#
# Usage:
#   ./_run.sh <target> <command>
#
# Arguments:
#   target    local | dev | prod   (selects _manifest.<target>.env)
#   command   up | down | restart | ps | logs
#
# Examples:
#   ./_run.sh local up        # create network + start every listed component
#   ./_run.sh local down      # stop every listed component (network kept)
#   ./_run.sh local ps        # show container status (per manifest.local)
#
# Manifest format — envs/_manifest.<target>.env:
#   INFERENCES="name1 name2 ..."
#   AUDIO="name1 name2 ..."
#   NETWORKS="name1 name2 ..."
# Names correspond to directories under
# deployment/{inferences,audio,networks}/<name>/.
# Missing directories are logged as warnings and skipped (the entire run does
# NOT abort).
set -euo pipefail

TARGET="${1:?usage: _run.sh <local|dev|prod> <up|down|restart|ps|logs>}"
CMD="${2:?usage: _run.sh <local|dev|prod> <up|down|restart|ps|logs>}"

# External docker networks that must exist before any component comes up.
NETWORKS_TO_CREATE=(
  "spark-inference-net"     # litellm gateway + inference backends
)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ──────────────── Load manifest ────────────────

MANIFEST="../envs/_manifest.${TARGET}.env"
if [ ! -f "$MANIFEST" ]; then
  echo "error: manifest not found: $MANIFEST" >&2
  echo "hint:  cp ../envs/_manifest.example.env $MANIFEST" >&2
  echo "       then edit it to list the components you want to boot." >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$MANIFEST"

INFERENCES="${INFERENCES:-}"
AUDIO="${AUDIO:-}"
NETWORKS="${NETWORKS:-}"

if [ -z "$INFERENCES" ] && [ -z "$AUDIO" ] && [ -z "$NETWORKS" ]; then
  echo "error: manifest $MANIFEST defines no INFERENCES / AUDIO / NETWORKS" >&2
  exit 1
fi

echo "── manifest: $MANIFEST"
echo "   INFERENCES : ${INFERENCES:-<none>}"
echo "   AUDIO      : ${AUDIO:-<none>}"
echo "   NETWORKS   : ${NETWORKS:-<none>}"

# ──────────────── Helpers ────────────────

ensure_network() {
  local net
  for net in "${NETWORKS_TO_CREATE[@]}"; do
    if ! docker network inspect "$net" >/dev/null 2>&1; then
      echo ">>> creating docker network: $net"
      docker network create "$net"
    fi
  done
}

run_component() {
  local category="$1"
  local name="$2"
  local subcommand="$3"
  local component="${category}/${name}"

  if [ ! -d "$component" ]; then
    echo "::warning:: ${component} listed in manifest but directory missing — skipping"
    return 0
  fi
  if [ ! -x "${component}/run.sh" ]; then
    echo "::warning:: ${component}/run.sh not executable — skipping"
    return 0
  fi

  echo
  echo ">>> ${component} : ${subcommand}"
  ( cd "$component" && ./run.sh "$TARGET" "$subcommand" )
}

for_each_up() {
  # Boot order: inferences (slow LLM load) → audio (fast FastAPI build/start) →
  # networks (gateway) last so every upstream is ready before clients hit the
  # gateway.
  for name in $INFERENCES; do run_component "inferences" "$name" up; done
  for name in $AUDIO;      do run_component "audio"      "$name" up; done
  for name in $NETWORKS;   do run_component "networks"   "$name" up; done
}

for_each_down() {
  for name in $NETWORKS;   do run_component "networks"   "$name" down || true; done
  for name in $AUDIO;      do run_component "audio"      "$name" down || true; done
  for name in $INFERENCES; do run_component "inferences" "$name" down || true; done
}

for_each_cmd() {
  local subcommand="$1"
  for name in $INFERENCES; do run_component "inferences" "$name" "$subcommand" || true; done
  for name in $AUDIO;      do run_component "audio"      "$name" "$subcommand" || true; done
  for name in $NETWORKS;   do run_component "networks"   "$name" "$subcommand" || true; done
}

# ──────────────── Dispatch ────────────────

case "$CMD" in
  up)
    ensure_network
    for_each_up
    ;;
  down)
    for_each_down
    ;;
  restart)
    for_each_cmd restart
    ;;
  ps)
    for_each_cmd ps
    ;;
  logs)
    for_each_cmd logs
    ;;
  *)
    echo "error: unknown command '$CMD' (expected: up|down|restart|ps|logs)" >&2
    exit 1
    ;;
esac
