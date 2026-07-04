#!/usr/bin/env bash
# TIBM3 — verify Celery bars path uses Platform IB Gateway fetch_bars_range RPC (no direct TWS).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
source "$ENV_FILE"

REDIS_URL="redis://trade-prod:${REDIS_IB_TRADE_PROD_PASS}@127.0.0.1:6379"

rpc_op() {
  local op="$1"
  local payload="${2-}"
  if [[ -z "$payload" ]]; then
    payload='{}'
  fi
  local req_id="celery-bars-$(date +%s)-${RANDOM}"
  kubectl exec -n data deploy/redis-ib -- redis-cli -u "$REDIS_URL" --no-auth-warning \
    XADD ib:operator:cmd '*' req_id "$req_id" v 1 op "$op" payload "$payload" caller verify-celery-bars >/dev/null
  sleep 5
  local result
  result=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "$REDIS_URL" --no-auth-warning GET "ib:operator:result:${req_id}")
  if [[ -z "$result" || "$result" != *'"ok": true'* && "$result" != *'"ok":true'* ]]; then
    echo "ERROR: op=$op result=$result" >&2
    exit 1
  fi
  echo "  $op OK"
}

echo "== [1/3] Gateway pod ready =="
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=ib-gateway -n data --timeout=60s

echo "== [2/3] Operator ping (Celery bars ensure_connected) =="
rpc_op ping '{}'

echo "== [3/3] fetch_bars_range (Celery bars backfill RPC) =="
rpc_op fetch_bars_range '{"symbol":"SPY","period":"1 D"}'

echo
echo "Trade Celery bars (TIBM3) verification OK — worker must use ib_operator.use_for_celery_bars (default true)"
