#!/usr/bin/env bash
# Start the API briefly and hit each endpoint against the seeded dev database.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run uvicorn app.main:app --port 8077 >/tmp/claim-integrity-smoke.log 2>&1 &
pid=$!
trap 'kill $pid' EXIT
for _ in $(seq 30); do curl -sf localhost:8077/health >/dev/null && break; sleep 0.5; done
curl -s localhost:8077/health; echo
sku=$(curl -s localhost:8077/skus | uv run python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
curl -s -X POST "localhost:8077/skus/$sku/run" | uv run python -c 'import json,sys; [print(c["verdict"], c["severity"], c["field"]) for c in json.load(sys.stdin)]'
curl -s "localhost:8077/skus/$sku/conflicts" | uv run python -c 'import json,sys; print(len(json.load(sys.stdin)), "conflicts stored")'
