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

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $1 == key {
      sub(/^[^=]*=/, "")
      print
    }
  ' "$ENV_FILE" | tail -n 1
}

CODEX_ENABLED_RAW="$(env_value GATEWAY_CODEX_ENABLED)"
CODEX_ENABLED_RAW="${CODEX_ENABLED_RAW:-$(env_value GATEWAY_CODEX_OCR_ENABLED)}"
CODEX_ENABLED="$(printf '%s' "$CODEX_ENABLED_RAW" | tr '[:upper:]' '[:lower:]')"

COMPOSE_ARGS=(--env-file "$ENV_FILE" -f docker-compose.yml)
case "$CODEX_ENABLED" in
  1|true|yes|on)
    if [ -z "$(env_value GATEWAY_CODEX_AUTH_DIR)" ]; then
      echo "error: GATEWAY_CODEX_AUTH_DIR required when GATEWAY_CODEX_ENABLED=true" >&2
      echo "hint: set GATEWAY_CODEX_AUTH_DIR=/home/<user>/.codex in $ENV_FILE" >&2
      exit 1
    fi
    COMPOSE_ARGS+=(-f docker-compose.codex.yml)
    ;;
esac

# `up` 과 `restart` 시점에 라우팅 재렌더링 — 매니페스트 변경이 즉시 반영되도록.
case "$CMD" in
  up|restart)
    ./render.sh "$TARGET"
    ;;
esac

case "$CMD" in
  up)       docker compose "${COMPOSE_ARGS[@]}" up -d --build ;;
  down)     docker compose "${COMPOSE_ARGS[@]}" down ;;
  # `--force-recreate` 필수: routes.rendered.yaml 가 bind-mount 라 내용
  # 변경만으로는 compose 가 재생성 트리거 X → 신규 라우트가 반영 안 됨.
  # 게이트웨이는 startup 시 한 번만 routes 파일을 읽으므로 컨테이너 자체를
  # 재생성해야 새 라우트가 픽업된다.
  restart)  docker compose "${COMPOSE_ARGS[@]}" up -d --build --force-recreate ;;
  ps)       docker compose "${COMPOSE_ARGS[@]}" ps ;;
  logs)     docker compose "${COMPOSE_ARGS[@]}" logs -f --tail=200 ;;
  *)        echo "error: unknown command '$CMD'" >&2; exit 1 ;;
esac
