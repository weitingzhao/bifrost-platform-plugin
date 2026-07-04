#!/usr/bin/env bash
# Verify IB Gateway Plugin on K3s.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
source "$ENV_FILE"

echo "== ib-gateway pod =="
kubectl get pods,deploy -n data -l app.kubernetes.io/name=ib-gateway
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=ib-gateway -n data --timeout=60s

echo "== legacy health keys on redis-ib =="
kubectl exec -n data deploy/redis-ib -- redis-cli -u "redis://ib-gateway:${REDIS_IB_GATEWAY_PASS}@127.0.0.1:6379" HGETALL bifrost:health:ws_ib_ingestor | head -20

echo "== sample tick (canonical STK contract_key) =="
TICK=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "redis://ib-gateway:${REDIS_IB_GATEWAY_PASS}@127.0.0.1:6379" --no-auth-warning GET "ib:ingester:tick:NVDA|STK|||")
echo "$TICK" | head -c 200
echo
if [[ -z "$TICK" || "$TICK" != *"bid"* ]]; then
  echo "ERROR: NVDA tick missing or not from mock/live gateway" >&2
  exit 1
fi

echo "== operator ping RPC =="
REQ_ID="phase1-$(date +%s)"
kubectl exec -n data deploy/redis-ib -- redis-cli -u "redis://trade-prod:${REDIS_IB_TRADE_PROD_PASS}@127.0.0.1:6379" \
  XADD ib:operator:cmd '*' req_id "$REQ_ID" v 1 op ping payload '{}' caller verify
sleep 3
RESULT=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "redis://trade-prod:${REDIS_IB_TRADE_PROD_PASS}@127.0.0.1:6379" GET "ib:operator:result:${REQ_ID}")
echo "$RESULT"
if [[ -z "$RESULT" || "$RESULT" != *'"ok"'* ]]; then
  echo "ERROR: operator ping result missing or not ok" >&2
  exit 1
fi

echo
echo "ib-gateway verification OK"
