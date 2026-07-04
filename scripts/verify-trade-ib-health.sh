#!/usr/bin/env bash
# TIBM2 — verify Trade IB health keys come from Platform Gateway @ redis-ib.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
source "$ENV_FILE"

GW_URL="redis://ib-gateway:${REDIS_IB_GATEWAY_PASS}@127.0.0.1:6379"

check_hash() {
  local key="$1"
  local label="$2"
  local plugin mode
  plugin=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "$GW_URL" --no-auth-warning HGET "$key" plugin)
  mode=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "$GW_URL" --no-auth-warning HGET "$key" mode)
  if [[ "$plugin" != "ib-gateway" ]]; then
    echo "ERROR: $label missing plugin=ib-gateway (got $plugin)" >&2
    exit 1
  fi
  if [[ "$mode" != "live" && "$mode" != "mock" ]]; then
    echo "ERROR: $label mode not live/mock (got $mode)" >&2
    exit 1
  fi
  echo "  $label OK plugin=$plugin mode=$mode"
}

echo "== [1/3] Gateway pod ready =="
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=ib-gateway -n data --timeout=60s

echo "== [2/3] Platform Gateway health hashes on redis-ib =="
check_hash "bifrost:health:ws_ib_ingestor" "ingestor"
check_hash "bifrost:health:ws_ib_account_agent" "account_agent"
check_hash "bifrost:health:ws_ib_operator" "operator"

echo "== [3/3] Canonical tick read path (S01) =="
INGESTOR_MODE=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "$GW_URL" --no-auth-warning HGET "bifrost:health:ws_ib_ingestor" mode)
if [[ "$INGESTOR_MODE" == "mock" ]]; then
  echo "  WARN: ingestor mode=mock — skip NVDA tick (live TWS not required for STG rollout)"
else
  TICK=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "$GW_URL" --no-auth-warning GET "ib:ingester:tick:NVDA|STK|||")
  if [[ -z "$TICK" || "$TICK" != *"bid"* ]]; then
    echo "ERROR: NVDA tick missing on redis-ib" >&2
    exit 1
  fi
  echo "  tick NVDA OK"
fi

echo
echo "Trade IB health (TIBM2) verification OK — Monitor API should expose socket.platform_ib_gateway after bifrost-core 0.2.9 deploy"
