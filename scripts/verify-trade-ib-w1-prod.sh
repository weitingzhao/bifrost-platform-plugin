#!/usr/bin/env bash
# TIBM Rollout W1 — runtime verify prod observability plane after image rollout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
# shellcheck disable=SC1091
source "$(dirname "$0")/lib/tibm_prod_defaults.sh"
NS="${PROD_NAMESPACE}"
PROD_HOST="${PROD_GATEWAY_HOST}"
PROD_IP="${PROD_GATEWAY_IP}"

echo "== TIBM W1 prod runtime verify =="
echo

echo "== [1/6] W1 deployments ready =="
for dep in api-monitor api-ops frontend; do
  kubectl wait --for=condition=available "deployment/${dep}" -n "${NS}" --timeout=120s
  echo "  ${dep} available"
done

echo "== [2/6] Daemon observe-safe (D10 — no live orders) =="
daemon_replicas=$(kubectl get deploy daemon -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "missing")
if [[ "$daemon_replicas" -lt 1 ]]; then
  echo "ERROR: daemon replicas=${daemon_replicas} (prod observe-safe expects >=1)" >&2
  exit 1
fi
echo "  daemon replicas=${daemon_replicas} OK (observe mode — not a W1 rollout target)"

echo "== [3/6] Legacy IB socket StatefulSets absent =="
for sts in ib-market-gateway ib-account-agent ib-operator; do
  if kubectl get "statefulset/${sts}" -n "${NS}" >/dev/null 2>&1; then
    echo "ERROR: legacy statefulset/${sts} still present — retire before prod TIBM rollout" >&2
    exit 1
  fi
  echo "  statefulset/${sts} absent OK"
done

echo "== [4/6] bifrost-core platform_ib_gateway in api-monitor pod =="
kubectl exec -n "${NS}" deploy/api-monitor -- python -c "
import importlib.util
assert importlib.util.find_spec('bifrost_core.monitor.integrations.platform_ib_gateway'), 'missing platform_ib_gateway'
print('  platform_ib_gateway module OK')
"

echo "== [5/6] Monitor /status — socket.platform_ib_gateway =="
status_json=$(curl -sf -H "Host: ${PROD_HOST}" "http://${PROD_IP}/api/monitor/status")
if ! python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert d.get('socket',{}).get('platform_ib_gateway') is not None" "$status_json"; then
  echo "ERROR: socket.platform_ib_gateway missing in Monitor /status" >&2
  echo "$status_json" | python3 -m json.tool | head -40 >&2 || true
  exit 1
fi
echo "  platform_ib_gateway present in /status"

echo "== [6/6] Source + redis health (TIBM4 subset) =="
make -C "$ROOT" verify-trade-ib-ui

echo
echo "TIBM W1 prod runtime verification OK"
