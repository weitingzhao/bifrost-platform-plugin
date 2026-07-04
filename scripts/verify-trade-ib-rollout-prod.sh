#!/usr/bin/env bash
# TIBM Rollout prod complete — aggregate W1+W2+W3 + program verify + D10 observe-safe guards.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
# shellcheck disable=SC1091
source "$(dirname "$0")/lib/tibm_prod_defaults.sh"
NS="${PROD_NAMESPACE}"
PROD_HOST="${PROD_GATEWAY_HOST}"
PROD_IP="${PROD_GATEWAY_IP}"
MIN_CORE="${TIBM_ROLLOUT_MIN_CORE:-0.2.10}"

echo "== TIBM Rollout prod complete verify =="
echo

echo "== [1/6] Wave gates W1 + W2 + W3 =="
make -C "$ROOT" verify-trade-ib-w1-prod
make -C "$ROOT" verify-trade-ib-w2-prod
make -C "$ROOT" verify-trade-ib-w3-prod

echo "== [2/6] Program aggregate (TIBM-PC-1 subset) =="
make -C "$ROOT" verify-trade-ib-migration-program

echo "== [3/6] Prod rolled workloads — bifrost-core >= ${MIN_CORE} =="
ROLLED_PYTHON_DEPLOYMENTS=(
  api-monitor api-ops
  celery-worker
  api-market api-massive api-research api-portfolio api-docs api-trading
)
for dep in "${ROLLED_PYTHON_DEPLOYMENTS[@]}"; do
  kubectl exec -n "${NS}" "deploy/${dep}" -- python -c "
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
        raise SystemExit(f'ERROR: ${dep} bifrost-core {v} < ${MIN_CORE}')
print(f'  ${dep} bifrost-core {v} OK')
"
done
kubectl wait --for=condition=available "deployment/frontend" -n "${NS}" --timeout=60s >/dev/null
echo "  frontend available (Node image — W1 + TIBM4 UI gate covers FE rollout)"

echo "== [4/6] D10 / W-block guards (prod observe-safe) =="
daemon_replicas=$(kubectl get deploy daemon -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "missing")
if [[ "$daemon_replicas" -lt 1 ]]; then
  echo "ERROR: daemon replicas=${daemon_replicas} (prod observe-safe expects >=1)" >&2
  exit 1
fi
echo "  daemon replicas=${daemon_replicas} OK (observe mode — no live order placement)"

for sts in ib-market-gateway ib-account-agent ib-operator; do
  if kubectl get "statefulset/${sts}" -n "${NS}" >/dev/null 2>&1; then
    echo "ERROR: legacy statefulset/${sts} still present on prod" >&2
    exit 1
  fi
done
echo "  legacy IB socket StatefulSets absent OK"

strategy_core=$(kubectl exec -n "${NS}" deploy/api-strategy -- python -c \
  "import importlib.metadata as m; print(m.version('bifrost-core'))" 2>/dev/null || echo "unknown")
echo "  api-strategy bifrost-core=${strategy_core} (out of W1–W3 scope — not a rollout gate)"

echo "== [5/6] Monitor platform_ib_gateway via prod gateway =="
status_json=$(curl -sf -H "Host: ${PROD_HOST}" "http://${PROD_IP}/api/monitor/status")
python3 -c "
import json, sys
d = json.loads(sys.argv[1])
assert d.get('socket', {}).get('platform_ib_gateway') is not None, 'platform_ib_gateway missing'
print('  socket.platform_ib_gateway present OK')
" "$status_json"

echo "== [6/6] Prod gateway health subset =="
fe_code=$(curl -sf -o /dev/null -w "%{http_code}" -H "Host: ${PROD_HOST}" "http://${PROD_IP}/" || echo "000")
if [[ "$fe_code" != "200" ]]; then
  echo "ERROR: prod frontend HTTP ${fe_code}" >&2
  exit 1
fi
echo "  frontend HTTP 200 OK"

echo
echo "TIBM Rollout prod complete verification OK"
