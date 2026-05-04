#!/usr/bin/env bash
# Template run.sh — leave the COMPONENT_REL line as `audio/$(basename ...)`.
# It auto-resolves so you don't need to edit this file when copying the template.
#
# `up` 은 `--build` 와 함께 — audio 컴포넌트는 로컬에서 이미지를 빌드 한다
# (vLLM/TEI 처럼 사전 빌드 이미지가 아님).
set -euo pipefail

TARGET="${1:?usage: run.sh <local|dev|prod> <up|down|restart|ps|logs>}"
CMD="${2:?usage: run.sh <local|dev|prod> <up|down|restart|ps|logs>}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

COMPONENT_REL="audio/$(basename "$SCRIPT_DIR")"
ENV_FILE="../../../envs/${COMPONENT_REL}/.env.${TARGET}"

if [ ! -f "$ENV_FILE" ]; then
  echo "error: env file not found: $(realpath "$ENV_FILE" 2>/dev/null || echo "$ENV_FILE")" >&2
  echo "hint: cp ../../../envs/${COMPONENT_REL}/.env.example ../../../envs/${COMPONENT_REL}/.env.${TARGET}" >&2
  exit 1
fi

case "$CMD" in
  up)       docker compose --env-file "$ENV_FILE" up -d --build ;;
  down)     docker compose --env-file "$ENV_FILE" down ;;
  restart)  docker compose --env-file "$ENV_FILE" restart ;;
  ps)       docker compose --env-file "$ENV_FILE" ps ;;
  logs)     docker compose --env-file "$ENV_FILE" logs -f --tail=200 ;;
  *)        echo "error: unknown command '$CMD'" >&2; exit 1 ;;
esac
