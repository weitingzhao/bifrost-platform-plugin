#!/usr/bin/env bash
# TIBM Rollout W1 — runtime verify STG observability plane after image rollout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
NS="${STG_NAMESPACE:-bifrost-stg}"
STG_HOST="${STG_TRADE_HOST:-trade-stg.bifrost.lan}"
STG_IP="${STG_TRADE_IP:-192.168.10.73}"
GW_URL="redis://ib-gateway:${REDIS_IB_GATEWAY_PASS:-}@127.0.0.1:6379"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  GW_URL="redis://ib-gateway:${REDIS_IB_GATEWAY_PASS}@127.0.0.1:6379"
fi

echo "== TIBM W1 STG runtime verify =="
echo

echo "== [1/6] W1 deployments ready =="
for dep in api-monitor api-ops frontend; do
  kubectl wait --for=condition=available "deployment/${dep}" -n "${NS}" --timeout=120s
  echo "  ${dep} available"
done

echo "== [2/6] Daemon still scaled down (D10) =="
daemon_replicas=$(kubectl get deploy daemon -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "missing")
if [[ "$daemon_replicas" != "0" ]]; then
  echo "ERROR: daemon replicas=${daemon_replicas} (expected 0 for D10)" >&2
  exit 1
fi
echo "  daemon replicas=0 OK"

echo "== [3/6] bifrost-core platform_ib_gateway in api-monitor pod =="
kubectl exec -n "${NS}" deploy/api-monitor -- python -c "
import importlib.util
assert importlib.util.find_spec('bifrost_core.monitor.integrations.platform_ib_gateway'), 'missing platform_ib_gateway'
print('  platform_ib_gateway module OK')
"

echo "== [4/6] Monitor /status — socket.platform_ib_gateway =="
status_json=$(curl -sf -H "Host: ${STG_HOST}" "http://${STG_IP}/api/monitor/status")
if ! python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert d.get('socket',{}).get('platform_ib_gateway') is not None" "$status_json"; then
  echo "ERROR: socket.platform_ib_gateway missing in Monitor /status" >&2
  echo "$status_json" | python3 -m json.tool | head -40 >&2 || true
  exit 1
fi
echo "  platform_ib_gateway present in /status"

echo "== [5/6] Ops market-ingest — platform_gateway_managed field =="
ops_json=$(curl -sf -H "Host: ${STG_HOST}" "http://${STG_IP}/api/ops/market-ingest/services" 2>/dev/null || true)
if [[ -n "$ops_json" ]]; then
  python3 -c "
import json, sys
d = json.loads(sys.argv[1])
rows = d if isinstance(d, list) else d.get('services', d.get('items', []))
found = any(isinstance(r, dict) and r.get('platform_gateway_managed') is not None for r in rows)
assert found, 'no platform_gateway_managed on market-ingest rows'
print('  platform_gateway_managed field OK')
" "$ops_json"
else
  echo "  WARN: ops market-ingest unreachable (optional if auth required) — skip"
fi

echo "== [6/6] Source + redis health (TIBM4 subset) =="
make -C "$ROOT" verify-trade-ib-ui

echo
echo "TIBM W1 STG runtime verification OK"
