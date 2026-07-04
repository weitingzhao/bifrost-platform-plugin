#!/usr/bin/env bash
# IBGP4 — verify ib-gateway live mode (real TWS @ .30/.32).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
PLATFORM_API="${PLATFORM_API:-http://127.0.0.1:8780}"
export KUBECONFIG

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

echo "== [1/4] ConfigMap mode =="
MODE=$(kubectl get configmap ib-gateway-config -n data -o jsonpath='{.data.mode}')
echo "  mode=$MODE"
if [[ "$MODE" != "live" ]]; then
  echo "FAIL expected mode=live (patch via Console or POST .../control/mode)" >&2
  exit 1
fi

echo "== [2/4] Deployment ready =="
kubectl wait --for=condition=available deployment/ib-gateway -n data --timeout=120s
kubectl get deploy ib-gateway -n data -o jsonpath='{.status.readyReplicas}/{.spec.replicas} ready' && echo

echo "== [3/4] platform-api status (live slots) =="
STATUS=$(curl -sS "${PLATFORM_API}/api/v1/plugins/ib-gateway/status")
echo "$STATUS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('mode') == 'live', f\"mode={d.get('mode')}\"
assert d.get('reachability') in ('ok', 'degraded'), d.get('reachability')
slots = d.get('slots') or []
assert len(slots) >= 2, slots
for s in slots:
    assert s.get('connected') is True, s
print('  mode=live reachability=', d.get('reachability'))
for s in slots:
    print(f\"  slot {s.get('slot')} {s.get('account_id')} connected={s.get('connected')}\")
"

echo "== [4/4] redis-ib live health + operator ping =="
kubectl exec -n data deploy/redis-ib -- redis-cli -u "redis://ib-gateway:${REDIS_IB_GATEWAY_PASS}@127.0.0.1:6379" \
  HGET bifrost:health:ws_ib_ingestor mode
# shellcheck disable=SC1091
source "$(dirname "$0")/lib/redis_operator_ping.sh"
REQ_ID="live-verify-$$"
RESULT=$(redis_operator_ping "redis://trade-prod:${REDIS_IB_TRADE_PROD_PASS}@127.0.0.1:6379" "$REQ_ID" 15)
echo "$RESULT" | grep -q '"ok"' || { echo "FAIL operator ping: $RESULT" >&2; exit 1; }
echo "  operator ping OK"

echo "IBGP4 Live TWS verification OK"
