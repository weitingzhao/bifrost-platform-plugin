#!/usr/bin/env bash
# TIBM4 — verify Trade UI/ops paths reflect Platform IB Gateway (not legacy socket STS).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
source "$ENV_FILE"

GW_URL="redis://ib-gateway:${REDIS_IB_GATEWAY_PASS}@127.0.0.1:6379"

echo "== [1/4] Gateway pod ready =="
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=ib-gateway -n data --timeout=60s

echo "== [2/4] Health hashes tagged plugin=ib-gateway =="
for key in bifrost:health:ws_ib_ingestor bifrost:health:ws_ib_account_agent bifrost:health:ws_ib_operator; do
  plugin=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "$GW_URL" --no-auth-warning HGET "$key" plugin)
  if [[ "$plugin" != "ib-gateway" ]]; then
    echo "ERROR: $key plugin=$plugin (expected ib-gateway)" >&2
    exit 1
  fi
  echo "  $key OK"
done

echo "== [3/4] Ops market-ingest default labels (source grep) =="
if ! grep -q 'Platform IB Gateway' "$ROOT/../bifrost-trade-api/src/bifrost_api/ops/market_ingest_config.py"; then
  echo "ERROR: market_ingest_config.py missing Platform IB Gateway labels" >&2
  exit 1
fi
echo "  market_ingest_config.py labels OK"

echo "== [4/4] FE platformIbGateway module present =="
FE="$ROOT/../bifrost-trade-frontend/src/utils/platformIbGateway.ts"
if [[ ! -f "$FE" ]]; then
  echo "ERROR: missing $FE" >&2
  exit 1
fi
echo "  platformIbGateway.ts OK"

echo
echo "Trade IB UI/legacy (TIBM4) verification OK — Monitor /status platform_ib_gateway visible after core 0.2.9+ deploy"
