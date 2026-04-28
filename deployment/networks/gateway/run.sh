#!/usr/bin/env bash
# networks/gateway — run.sh
# 부팅 전에 매니페스트 → routes.rendered.yaml 렌더링 후 docker compose up.
set -euo pipefail

TARGET="${1:?usage: run.sh <local|dev|prod> <up|down|restart|ps|logs>}"
CMD="${2:?usage: run.sh <local|dev|prod> <up|down|restart|ps|logs>}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="../../../envs/networks/gateway/.env.${TARGET}"

if [ ! -f "$ENV_FILE" ]; then
  echo "error: env file not found: $(realpath "$ENV_FILE" 2>/dev/null || echo "$ENV_FILE")" >&2
  echo "hint: cp ../../../envs/networks/gateway/.env.example ../../../envs/networks/gateway/.env.${TARGET}" >&2
  exit 1
fi

# `up` 과 `restart` 시점에 라우팅 재렌더링 — 매니페스트 변경이 즉시 반영되도록.
case "$CMD" in
  up|restart)
    ./render.sh "$TARGET"
    ;;
esac

case "$CMD" in
  up)       docker compose --env-file "$ENV_FILE" up -d --build ;;
  down)     docker compose --env-file "$ENV_FILE" down ;;
  restart)  docker compose --env-file "$ENV_FILE" up -d --build ;;
  ps)       docker compose --env-file "$ENV_FILE" ps ;;
  logs)     docker compose --env-file "$ENV_FILE" logs -f --tail=200 ;;
  *)        echo "error: unknown command '$CMD'" >&2; exit 1 ;;
esac
