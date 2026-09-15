#!/usr/bin/env bash
#
# Every /dsh-api endpoint as a runnable curl. Assumes a dsh with dsh-api
# loaded is running on 127.0.0.1:$PORT (default 3080).
#
# Usage:
#   ./examples/curl.sh              # exercise the read routes
#   ./examples/curl.sh --write      # also POST /workspace/create & /language

set -euo pipefail
PORT="${PORT:-3080}"
BASE="http://127.0.0.1:${PORT}/dsh-api"

echo "── GET  ${BASE}/health ──"
curl -sSf "${BASE}/health" | jq . || curl -sSf "${BASE}/health"

echo
echo "── GET  ${BASE}/language ──"
curl -sSf "${BASE}/language" | jq . || curl -sSf "${BASE}/language"

echo
echo "── GET  ${BASE}/workspace/list ──"
curl -sSf "${BASE}/workspace/list" | jq . || curl -sSf "${BASE}/workspace/list"

echo
echo "── GET  ${BASE}/workspace/current ──"
curl -sSf "${BASE}/workspace/current" | jq . || curl -sSf "${BASE}/workspace/current"

if [[ "${1:-}" == "--write" ]]; then
  echo
  echo "── POST ${BASE}/language ──"
  curl -sSf -X POST -H 'content-type: application/json' \
    -d '{"language":"zh"}' "${BASE}/language" | jq .

  TMP="$(mktemp -d)"
  echo
  echo "── POST ${BASE}/workspace/create  path=${TMP} ──"
  curl -sSf -X POST -H 'content-type: application/json' \
    -d "{\"path\":\"${TMP}\",\"title\":\"curl-example\"}" \
    "${BASE}/workspace/create" | jq .
fi

echo
echo "── GET  ${BASE}/events  (5s SSE preview) ──"
curl -sN --max-time 5 "${BASE}/events" | head -20 || true
echo "── SSE closed ──"
