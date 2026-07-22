#!/usr/bin/env bash
# TIBM Rollout STG complete — aggregate W1+W2+W3 + program verify + D10 guards.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
NS="${STG_NAMESPACE:-bifrost-stg}"
MIN_CORE="${TIBM_ROLLOUT_MIN_CORE:-0.2.10}"

echo "== TIBM Rollout STG complete verify =="
echo

echo "== [1/5] Wave gates W1 + W2 + W3 =="
make -C "$ROOT" verify-trade-ib-w1-stg
make -C "$ROOT" verify-trade-ib-w2-stg
make -C "$ROOT" verify-trade-ib-w3-stg

echo "== [2/5] Program aggregate (TIBM-PC-1 subset) =="
make -C "$ROOT" verify-trade-ib-migration-program

echo "== [3/5] STG rolled workloads — bifrost-core >= ${MIN_CORE} =="
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

echo "== [4/5] D10 / W-block guards =="
daemon_replicas=$(kubectl get deploy daemon -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "missing")
if [[ "$daemon_replicas" != "0" ]]; then
  echo "ERROR: daemon replicas=${daemon_replicas} (D10 requires 0 on STG)" >&2
  exit 1
fi
echo "  daemon replicas=0 OK (D10 BLOCKED)"

strategy_core=$(kubectl exec -n "${NS}" deploy/api-strategy -- python -c \
  "import importlib.metadata as m; print(m.version('bifrost-core'))" 2>/dev/null || echo "unknown")
echo "  api-strategy bifrost-core=${strategy_core} (out of W1–W3 scope — not a rollout gate)"

echo "== [5/5] Monitor platform_ib_gateway still present =="
STG_BASE_URL="${STG_TRADE_BASE_URL:-http://192.168.10.73:30880}"
STG_HOST="${STG_TRADE_HOST:-}"
if [[ -n "${STG_HOST}" ]]; then
  status_json=$(curl -sf -H "Host: ${STG_HOST}" "${STG_BASE_URL}/api/monitor/status")
else
  status_json=$(curl -sf "${STG_BASE_URL}/api/monitor/status")
fi
python3 -c "
import json, sys
d = json.loads(sys.argv[1])
assert d.get('socket', {}).get('platform_ib_gateway') is not None, 'platform_ib_gateway missing'
print('  socket.platform_ib_gateway present OK')
" "$status_json"

echo
echo "TIBM Rollout STG complete verification OK"
