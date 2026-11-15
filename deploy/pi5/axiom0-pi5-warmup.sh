#!/usr/bin/env bash
# Load AXIOM0_MODEL into Ollama ahead of the first question. Safe to run any time.
set -euo pipefail
MODEL="${AXIOM0_MODEL:-llama3.2:3b}"
KEEP="${AXIOM0_KEEP_ALIVE:-30m}"
API="http://127.0.0.1:11434"

for _ in $(seq 1 60); do
  curl -fsS -m 2 "$API/api/version" >/dev/null 2>&1 && break
  sleep 1
done

# keep_alive is a number for -1/0/seconds, a string for 30m / 2h.
if [[ "$KEEP" =~ ^-?[0-9]+$ ]]; then KA="$KEEP"; else KA="\"$KEEP\""; fi
if [[ ! "$MODEL" =~ ^[A-Za-z0-9._:/-]+$ ]]; then echo "warmup: invalid model name" >&2; exit 1; fi

START=$(date +%s)
if curl -fsS -m 280 "$API/api/generate" -d "{\"model\":\"$MODEL\",\"keep_alive\":$KA}" >/dev/null; then
  echo "warmup: $MODEL loaded in $(( $(date +%s) - START ))s (keep_alive=$KEEP)"
else
  echo "warmup: could not load $MODEL (is it pulled? run: ollama pull $MODEL)" >&2
  exit 1
fi
