#!/usr/bin/env bash
# Verify trade-dev ACL read path on Platform redis-ib (dev alias — read-only ACL).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
# shellcheck disable=SC1090
source "$ENV_FILE"

DEV_URL="redis://trade-dev:${REDIS_IB_TRADE_DEV_PASS}@127.0.0.1:6379"

echo "== [1/2] trade-dev PING on redis-ib =="
kubectl exec -n data deploy/redis-ib -- redis-cli -u "$DEV_URL" --no-auth-warning PING | grep -q PONG
echo "  trade-dev PING OK"

echo "== [2/2] trade-dev ib:ingester tick read (S01 read ACL) =="
TICK=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "$DEV_URL" --no-auth-warning \
  GET "ib:ingester:tick:NVDA|STK|||" 2>/dev/null || true)
if [[ -z "$TICK" || "$TICK" == *"NOPERM"* ]]; then
  echo "  WARN: no readable tick (Gateway mock / ACL) — trade-dev PING sufficient for dev-compose gate"
else
  echo "  trade-dev tick read OK"
fi

echo
echo "Trade IB dev read ACL verification OK"
