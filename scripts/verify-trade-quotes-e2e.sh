#!/usr/bin/env bash
# Trade Market quotes E2E — canonical tick key + optional HTTP /quotes (stg).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
TRADE_NS="${TRADE_NS:-bifrost-stg}"
GATEWAY_HOST="${STG_GATEWAY_HOST:-trade-stg.bifrost.lan}"
GATEWAY_IP="${STG_GATEWAY_IP:-192.168.10.73}"
PROBE_SYMBOL="${PROBE_SYMBOL:-NVDA}"
TICK_KEY="${PROBE_SYMBOL}|STK|||"

export KUBECONFIG

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

echo "== [1/3] redis-ib canonical tick key (${TICK_KEY}) =="
TICK_JSON=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u \
  "redis://trade-prod:${REDIS_IB_TRADE_PROD_PASS}@127.0.0.1:6379" \
  --no-auth-warning GET "ib:ingester:tick:${TICK_KEY}" 2>/dev/null || true)
if [[ -z "$TICK_JSON" || "$TICK_JSON" != *"contract_key"* ]]; then
  echo "FAIL missing tick at ib:ingester:tick:${TICK_KEY}" >&2
  echo "  hint: rollout ib-gateway after plugin tick-key fix" >&2
  exit 1
fi
echo "$TICK_JSON" | TICK_KEY="$TICK_KEY" python3 -c "
import json, sys, os
d = json.load(sys.stdin)
ck = os.environ['TICK_KEY']
assert d.get('contract_key') == ck, d.get('contract_key')
assert d.get('symbol') == ck.split('|', 1)[0], d.get('symbol')
print('  contract_key OK symbol=', d.get('symbol'))
"

echo "== [2/3] Trade pod redis-ib read (same key) =="
kubectl run "quotes-e2e-$$" -n "$TRADE_NS" --rm -i --restart=Never --image=redis:7-alpine --command -- \
  sh -c "nc -z redis-ib 6379 && redis-cli -h redis-ib -p 6379 --user trade-prod --pass '${REDIS_IB_TRADE_PROD_PASS}' --no-auth-warning GET 'ib:ingester:tick:${TICK_KEY}' | grep -q contract_key"
echo "  ${TRADE_NS} → redis-ib tick OK"

echo "== [3/3] Market API GET /quotes (HTTP via Traefik) =="
CORE_VER=$(kubectl exec -n "$TRADE_NS" deploy/api-market -- python3 -c "
import pkg_resources
print(pkg_resources.get_distribution('bifrost-core').version)
" 2>/dev/null || echo "unknown")
echo "  api-market bifrost-core=${CORE_VER}"

HTTP_BODY=$(curl -sf -H "Host: ${GATEWAY_HOST}" \
  "http://${GATEWAY_IP}/api/market/quotes?symbols=${PROBE_SYMBOL}" 2>/dev/null || echo '{}')
QUOTE_COUNT=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
qs = d.get('quotes') or []
print(len(qs))
" 2>/dev/null || echo 0)

if [[ "$QUOTE_COUNT" -ge 1 ]]; then
  echo "  /quotes returned ${QUOTE_COUNT} quote(s) OK"
elif python3 -c "import sys; v='${CORE_VER}'.split('.'); sys.exit(0 if len(v)>=3 and (int(v[0]),int(v[1]),int(v[2])) >= (0,2,8) else 1)" 2>/dev/null; then
  echo "FAIL /quotes empty with bifrost-core>=0.2.8 — rebuild api-market or check redis_ib config" >&2
  echo "  body: $(echo "$HTTP_BODY" | head -c 200)" >&2
  exit 1
else
  echo "  WARN /quotes empty (bifrost-core ${CORE_VER} < 0.2.8 — rebuild Trade images for HTTP E2E)"
fi

echo "Trade quotes E2E verification OK"
