#!/usr/bin/env bash
set -euo pipefail

: "${SERVICE_URL:?Set SERVICE_URL, e.g. https://your-service.run.app}"
: "${SHAHTRADINGAGENTS_API_TOKEN:?Set SHAHTRADINGAGENTS_API_TOKEN}"

base="${SERVICE_URL%/}"

echo "== health =="
curl --fail --silent --show-error "$base/health"
echo

echo "== ready =="
curl --fail --silent --show-error "$base/ready"
echo

echo "== unauthenticated analyze should be 401 =="
status=$(curl --silent --output /tmp/shah-noauth.json --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AMZN"}' \
  "$base/analyze")
if [[ "$status" != "401" ]]; then
  echo "Expected HTTP 401, got $status" >&2
  cat /tmp/shah-noauth.json >&2 || true
  exit 1
fi

echo "== authenticated AMZN analysis =="
curl --fail --silent --show-error \
  -H "Authorization: Bearer $SHAHTRADINGAGENTS_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "ticker": "AMZN",
    "asset_type": "stock",
    "analysts": ["market", "social", "news", "fundamentals"],
    "save_reports": true
  }' \
  "$base/analyze"
echo

echo "Smoke test passed."
