#!/usr/bin/env bash
# Launch the Control Center dashboard.
#
#   ./run.sh                 # uses config.yaml (or config.example.yaml)
#   CC_CONFIG=/path.yaml ./run.sh
#
# On first run this creates a local virtualenv and installs dependencies.
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
if [ ! -d "$VENV" ]; then
  echo "Creating virtualenv…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r requirements.txt
fi

# Read host/port/TLS/auth from the active config so we launch correctly.
read -r HOST PORT CERT KEY AUTH < <("$VENV/bin/python" - <<'PY'
from app.config import load_config
c = load_config()
print(c.host, c.port, c.tls.certfile or "-", c.tls.keyfile or "-", c.auth.enabled)
PY
)

ARGS=(app.main:app --host "$HOST" --port "$PORT")
SCHEME="http"
if [ "$CERT" != "-" ] && [ "$KEY" != "-" ]; then
  ARGS+=(--ssl-certfile "$CERT" --ssl-keyfile "$KEY")
  SCHEME="https"
fi

if [ "$AUTH" = "True" ] && [ -z "${CC_PASSWORD:-}" ]; then
  echo "NOTE: auth is enabled — set CC_PASSWORD (or auth.password_sha256 in config) or login will be impossible." >&2
fi

echo "Control Center → ${SCHEME}://${HOST}:${PORT}"
exec "$VENV/bin/uvicorn" "${ARGS[@]}"
