#!/usr/bin/env bash
# Verify Platform IB Gateway implements all ALL_OPS (RPC parity for TIBM1).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
source "$ENV_FILE"

REDIS_URL="redis://trade-prod:${REDIS_IB_TRADE_PROD_PASS}@127.0.0.1:6379"

rpc_ping() {
  local op="$1"
  local payload="${2-}"
  if [[ -z "$payload" ]]; then
    payload='{}'
  fi
  local req_id="rpc-parity-$(date +%s)-${RANDOM}"
  kubectl exec -n data deploy/redis-ib -- redis-cli -u "$REDIS_URL" --no-auth-warning \
    XADD ib:operator:cmd '*' req_id "$req_id" v 1 op "$op" payload "$payload" caller verify-rpc-parity >/dev/null
  sleep 5
  local result
  result=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "$REDIS_URL" --no-auth-warning GET "ib:operator:result:${req_id}")
  if [[ -z "$result" || "$result" != *'"ok": true'* && "$result" != *'"ok":true'* ]]; then
    echo "ERROR: op=$op result=$result" >&2
    exit 1
  fi
  echo "  $op OK"
}

echo "== [1/2] Gateway pod ready =="
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=ib-gateway -n data --timeout=60s

echo "== [2/2] ALL_OPS smoke via trade-prod ACL =="
rpc_ping ping '{}'
rpc_ping fetch_accounts_snapshot '{}'
rpc_ping fetch_bars '{"symbol":"NVDA","period":"1 day","duration":"1 D"}'
rpc_ping fetch_bars_range '{"symbol":"SPY","period":"1 D"}'
rpc_ping fetch_executions '{"days":1}'
rpc_ping fetch_option_expirations '{"symbol":"NVDA"}'
rpc_ping fetch_option_snapshot '{"symbol":"NVDA","expiration":"20260718","strikes":[130]}'
rpc_ping disconnect_all '{}'
rpc_ping reconnect_all '{}'

echo
echo "IB Gateway RPC parity verification OK (9/9 ops)"
