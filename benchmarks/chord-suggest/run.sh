#!/usr/bin/env bash
# Chord-suggest benchmark — fires the prompt set in prompts.jsonl against
# a LiteLLM gateway and records latency / token / JSON-validity metrics.
#
# Usage:
#   ./run.sh <model-alias> [reps] [outfile]
#
# Examples:
#   ./run.sh qwen3-8b 5 results-8b.csv
#   ./run.sh qwen3-32b 5 results-32b-fp8.csv
#
# Env (override defaults):
#   LITELLM_BASE_URL   default http://127.0.0.1:10080
#   LITELLM_API_KEY    default reads from envs/networks/litellm/.env.local
#
# Output: CSV with columns
#   prompt_id, rep, ttft_ms, total_ms, output_tokens, json_ok, raw_path
# Plus per-prompt raw response JSON saved under raw/<model>/<prompt_id>-<rep>.json
set -euo pipefail

MODEL="${1:?usage: run.sh <model-alias> [reps] [outfile]}"
REPS="${2:-5}"
OUT="${3:-results-${MODEL}.csv}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://127.0.0.1:10080}"
if [ -z "${LITELLM_API_KEY:-}" ]; then
  ENV_FILE="../../envs/networks/litellm/.env.local"
  if [ -f "$ENV_FILE" ]; then
    LITELLM_API_KEY="$(grep -E '^LITELLM_MASTER_KEY=' "$ENV_FILE" | cut -d= -f2-)"
  fi
fi
if [ -z "${LITELLM_API_KEY:-}" ]; then
  echo "error: LITELLM_API_KEY unset and could not read from $ENV_FILE" >&2
  exit 1
fi

PROMPTS="prompts.jsonl"
if [ ! -f "$PROMPTS" ]; then echo "error: $PROMPTS not found" >&2; exit 1; fi

RAW_DIR="raw/${MODEL}"
mkdir -p "$RAW_DIR"

echo "prompt_id,rep,ttft_ms,total_ms,output_tokens,json_ok,raw_path" > "$OUT"

SYSTEM_PROMPT='You are a chord progression assistant. Given a key and a list of chords played so far, suggest the next chord candidates that fit the key.

Always respond with strict JSON of the shape:
{"suggestions": ["Chord1", "Chord2", ...]}

Use standard chord symbols (e.g. C, Am, G7, Dm7, Bbmaj7). Do not include any prose, only the JSON.'

FEWSHOT_USER='Key: D major
Progression so far: D - Bm - G
Suggest 2 next chord candidates.'
FEWSHOT_ASSISTANT='{"suggestions": ["A", "F#m"]}'

while IFS= read -r line; do
  PROMPT_ID="$(jq -r '.id' <<< "$line")"
  KEY="$(jq -r '.key' <<< "$line")"
  CHORDS="$(jq -r '.chords | join(" - ")' <<< "$line")"
  N="$(jq -r '.n' <<< "$line")"
  USER_MSG="Key: ${KEY}
Progression so far: ${CHORDS}
Suggest ${N} next chord candidates."

  REQ_BODY="$(jq -n \
    --arg model "$MODEL" \
    --arg sys "$SYSTEM_PROMPT" \
    --arg fu "$FEWSHOT_USER" \
    --arg fa "$FEWSHOT_ASSISTANT" \
    --arg um "$USER_MSG" \
    '{
       model: $model,
       messages: [
         {role:"system", content:$sys},
         {role:"user", content:$fu},
         {role:"assistant", content:$fa},
         {role:"user", content:$um}
       ],
       response_format: {type:"json_object"},
       chat_template_kwargs: {enable_thinking: false},
       max_tokens: 256,
       temperature: 0.7,
       stream: true
     }')"

  for rep in $(seq 1 "$REPS"); do
    RAW="${RAW_DIR}/${PROMPT_ID}-${rep}.ndjson"
    : > "$RAW"

    START_NS=$(date +%s%N)
    FIRST_NS=""

    # Stream and capture first-token timestamp via process substitution.
    {
      curl -sS -N --no-buffer \
        -H "Authorization: Bearer ${LITELLM_API_KEY}" \
        -H 'Content-Type: application/json' \
        -d "$REQ_BODY" \
        "${LITELLM_BASE_URL}/v1/chat/completions"
    } | while IFS= read -r chunk; do
        # SSE prefix `data: ` strip
        case "$chunk" in
          "data: [DONE]") break ;;
          "data: "*)
            payload="${chunk#data: }"
            # First chunk with non-empty delta.content fires TTFT marker.
            if [ -z "$FIRST_NS" ]; then
              has_content="$(jq -r '.choices[0].delta.content // empty' <<< "$payload" 2>/dev/null || true)"
              if [ -n "$has_content" ]; then
                FIRST_NS=$(date +%s%N)
                echo "__TTFT__ ${FIRST_NS}" >> "$RAW"
              fi
            fi
            echo "$payload" >> "$RAW"
            ;;
          "") ;;
          *) echo "$chunk" >> "$RAW" ;;
        esac
      done
    END_NS=$(date +%s%N)

    # Re-derive metrics from the raw stream (subshell vars are lost above).
    FIRST_LINE="$(grep -m1 '^__TTFT__' "$RAW" || true)"
    if [ -n "$FIRST_LINE" ]; then
      FIRST_NS="${FIRST_LINE#__TTFT__ }"
      TTFT_MS=$(( (FIRST_NS - START_NS) / 1000000 ))
    else
      TTFT_MS=-1
    fi
    TOTAL_MS=$(( (END_NS - START_NS) / 1000000 ))

    # Reassemble the streamed assistant content for JSON validation.
    CONTENT="$(grep -v '^__TTFT__' "$RAW" \
      | jq -r 'select(. != "[DONE]") | .choices[0].delta.content // empty' 2>/dev/null \
      | tr -d '\n')"

    if echo "$CONTENT" | jq -e '.suggestions | type == "array"' >/dev/null 2>&1; then
      JSON_OK=1
    else
      JSON_OK=0
    fi

    # Output token estimate: word-ish split (no tokenizer here).
    OUT_TOK=$(printf '%s' "$CONTENT" | wc -w)

    echo "${PROMPT_ID},${rep},${TTFT_MS},${TOTAL_MS},${OUT_TOK},${JSON_OK},${RAW}" >> "$OUT"
    printf '  %-22s rep=%d  ttft=%5dms  total=%5dms  json_ok=%d\n' \
      "$PROMPT_ID" "$rep" "$TTFT_MS" "$TOTAL_MS" "$JSON_OK"
  done
done < "$PROMPTS"

echo
echo "── done. results: $OUT"
echo "── summary (median total_ms):"
awk -F, 'NR>1 {a[$1]=a[$1]" "$4} END {for (k in a) {n=split(a[k], v, " "); asort(v); print "  "k": p50="v[int(n/2)+1]"ms"}}' "$OUT" | sort
