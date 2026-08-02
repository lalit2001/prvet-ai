#!/bin/sh
# Write config.js from env at container start — one image, every deployment.
# See plan.md F9 AC9.2.
set -eu
API_URL="${CRV_API_BASE_URL:-http://localhost:8080}"
cat >/usr/share/nginx/html/config.js <<EOF
window.__CRV_CONFIG__ = { apiBaseUrl: "${API_URL}" };
EOF
