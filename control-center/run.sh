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

# Read host/port from the active config so the URL we print is correct.
read -r HOST PORT < <("$VENV/bin/python" - <<'PY'
from app.config import load_config
c = load_config()
print(c.host, c.port)
PY
)

echo "Control Center → http://${HOST}:${PORT}"
exec "$VENV/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT"
