#!/usr/bin/env bash
# Print the sha256 hash of a password, to paste into config.yaml as
# auth.password_sha256 (so the plaintext never lives in the file).
#
#   ./hash-password.sh 'my secret password'
#   ./hash-password.sh            # prompts without echoing
set -euo pipefail
if [ $# -ge 1 ]; then
  PW="$1"
else
  read -rs -p "Password: " PW; echo
fi
printf '%s' "$PW" | python3 -c "import sys,hashlib;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())"
