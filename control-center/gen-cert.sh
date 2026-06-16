#!/usr/bin/env bash
# Generate a self-signed TLS certificate for the Control Center.
# Good enough to encrypt traffic over an SSH tunnel or a private network.
# Browsers will warn (untrusted issuer); that's expected for self-signed certs.
#
#   ./gen-cert.sh            # writes certs/cert.pem + certs/key.pem
#
# Then point your config.yaml at them:
#   tls:
#     certfile: ./certs/cert.pem
#     keyfile:  ./certs/key.pem
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/key.pem -out certs/cert.pem \
  -days 825 -subj "/CN=control-center.local" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 certs/key.pem
echo "Wrote certs/cert.pem and certs/key.pem"
