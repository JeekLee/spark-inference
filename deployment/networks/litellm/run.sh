#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:?usage: run.sh <local|dev|prod> <up|down|restart|ps|logs>}"
CMD="${2:?usage: run.sh <local|dev|prod> <up|down|restart|ps|logs>}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

COMPONENT_REL="networks/litellm"
ENV_FILE="../../../envs/${COMPONENT_REL}/.env.${TARGET}"

if [ ! -f "$ENV_FILE" ]; then
  echo "error: env file not found: $(realpath "$ENV_FILE" 2>/dev/null || echo "$ENV_FILE")" >&2
  echo "hint: cp ../../../envs/${COMPONENT_REL}/.env.example ../../../envs/${COMPONENT_REL}/.env.${TARGET}" >&2
  exit 1
fi

case "$CMD" in
  up)       "./render.sh" "$TARGET"; docker compose --env-file "$ENV_FILE" up -d ;;
  down)     docker compose --env-file "$ENV_FILE" down ;;
  restart)  "./render.sh" "$TARGET"; docker compose --env-file "$ENV_FILE" restart ;;
  ps)       docker compose --env-file "$ENV_FILE" ps ;;
  logs)     docker compose --env-file "$ENV_FILE" logs -f --tail=200 ;;
  *)        echo "error: unknown command '$CMD'" >&2; exit 1 ;;
esac
