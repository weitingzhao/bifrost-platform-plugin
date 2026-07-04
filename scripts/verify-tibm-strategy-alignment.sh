#!/usr/bin/env bash
# Verify api-strategy bifrost-core >= 0.2.10 on STG + PROD after strategy rollout.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
MIN_CORE="${TIBM_STRATEGY_MIN_CORE:-0.2.10}"
PROD_HOST="${PROD_GATEWAY_HOST:-192.168.10.70}"
PROD_IP="${PROD_GATEWAY_IP:-192.168.10.70}"
STG_HOST="${STG_TRADE_HOST:-trade-stg.bifrost.lan}"
STG_IP="${STG_TRADE_IP:-192.168.10.73}"

check_core() {
  local ns="$1"
  kubectl exec -n "${ns}" deploy/api-strategy -- python -c "
import importlib.metadata as m
v = m.version('bifrost-core')
min_v = '${MIN_CORE}'.split('.')
cur = v.split('.')
for i in range(max(len(min_v), len(cur))):
    a = int(cur[i]) if i < len(cur) else 0
    b = int(min_v[i]) if i < len(min_v) else 0
    if a > b:
        break
    if a < b:
        raise SystemExit(f'ERROR: api-strategy bifrost-core {v} < ${MIN_CORE}')
print(f'  ${ns} api-strategy bifrost-core {v} OK')
"
}

echo "== TIBM api-strategy alignment verify =="
echo

echo "== [1/4] STG core version =="
check_core bifrost-stg

echo "== [2/4] PROD core version =="
check_core bifrost-prod

echo "== [3/4] HTTP /api/strategy/health =="
stg_code=$(curl -sf -o /dev/null -w "%{http_code}" -H "Host: ${STG_HOST}" \
  "http://${STG_IP}/api/strategy/health" || echo "000")
prod_lan_code=$(curl -sf -o /dev/null -w "%{http_code}" -H "Host: trade.bifrost.lan" \
  "http://${PROD_IP}/api/strategy/health" || echo "000")
prod_ip_code=$(curl -sf -o /dev/null -w "%{http_code}" -H "Host: ${PROD_HOST}" \
  "http://${PROD_IP}/api/strategy/health" || echo "000")
if [[ "$stg_code" != "200" ]]; then
  echo "ERROR: STG /api/strategy/health HTTP ${stg_code}" >&2
  exit 1
fi
if [[ "$prod_lan_code" != "200" ]]; then
  echo "ERROR: PROD trade.bifrost.lan /api/strategy/health HTTP ${prod_lan_code}" >&2
  exit 1
fi
echo "  STG HTTP 200 · PROD trade.bifrost.lan HTTP ${prod_lan_code} · PROD IP HTTP ${prod_ip_code}"

echo "== [4/4] D10 — no strategy gate mutations tested =="
echo "  read-only health gate only (live gate arming out of scope until D10 unlock)"

echo
echo "TIBM api-strategy alignment verification OK"
