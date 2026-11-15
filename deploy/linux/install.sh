#!/usr/bin/env bash
# AXIOM0 Living City — non-root local pilot bootstrap.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA="$ROOT/axiom0_data"
PY="${PYTHON:-python3}"
"$PY" - <<'PY'
import sys
if sys.version_info < (3, 11): raise SystemExit('Python 3.11+ required')
PY
"$PY" -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install -e "$ROOT"
"$ROOT/.venv/bin/python" -m axiom0 --data-dir "$DATA" init --admin "${AXIOM0_ADMIN:-howard}"
mkdir -p "$DATA"
chmod 700 "$DATA"
SECRET_FILE="$DATA/axiom0-secrets.env"
if [[ ! -f "$SECRET_FILE" ]]; then
  umask 077
  API="$($ROOT/.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  REVIEWER="$($ROOT/.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  printf 'AXIOM0_API_KEY=%s\nAXIOM0_REVIEWER_KEY=%s\nAXIOM0_REVIEWER_ID=local_reviewer\n' "$API" "$REVIEWER" > "$SECRET_FILE"
fi
chmod 600 "$SECRET_FILE"
"$ROOT/.venv/bin/python" -m axiom0 --data-dir "$DATA" doctor
echo "AXIOM0 installed as a local pilot. Start with: $ROOT/deploy/linux/start.sh"
echo 'No public server or scheduled feed-monitoring task was configured.'
