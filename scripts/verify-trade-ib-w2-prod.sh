#!/usr/bin/env bash
# TIBM Rollout W2 — runtime verify prod celery-worker after Platform IB Gateway bars rollout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
# shellcheck disable=SC1091
source "$(dirname "$0")/lib/tibm_prod_defaults.sh"
NS="${PROD_NAMESPACE}"
MIN_CORE_VERSION="${TIBM_W2_MIN_CORE_VERSION:-0.2.10}"

echo "== TIBM W2 prod runtime verify =="
echo

echo "== [1/7] celery-worker deployment ready =="
kubectl wait --for=condition=available "deployment/celery-worker" -n "${NS}" --timeout=120s
echo "  celery-worker available"

echo "== [2/7] Daemon observe-safe unchanged (D10) =="
daemon_replicas=$(kubectl get deploy daemon -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "missing")
if [[ "$daemon_replicas" -lt 1 ]]; then
  echo "ERROR: daemon replicas=${daemon_replicas} (prod observe-safe expects >=1)" >&2
  exit 1
fi
echo "  daemon replicas=${daemon_replicas} OK (W2 does not change daemon trading mode)"

echo "== [3/7] bifrost-core >= ${MIN_CORE_VERSION} in celery-worker pod =="
kubectl exec -n "${NS}" deploy/celery-worker -- python -c "
import importlib.metadata as m
v = m.version('bifrost-core')
min_v = '${MIN_CORE_VERSION}'.split('.')
cur = v.split('.')
for i in range(max(len(min_v), len(cur))):
    a = int(cur[i]) if i < len(cur) else 0
    b = int(min_v[i]) if i < len(min_v) else 0
    if a > b:
        break
    if a < b:
        raise SystemExit(f'ERROR: bifrost-core {v} < ${MIN_CORE_VERSION}')
print(f'  bifrost-core {v} OK')
"

echo "== [4/7] IbOperatorBarsAdapter import + use_for_celery_bars =="
kubectl exec -n "${NS}" deploy/celery-worker -- python -c "
import importlib.util
assert importlib.util.find_spec('bifrost_worker.data.bars.ib_operator_transport'), 'missing ib_operator_transport'
from bifrost_core.ib_operator.config import effective_ib_operator_settings
import yaml, os
with open(os.environ['BIFROST_CONFIG']) as f:
    cfg = yaml.safe_load(f)
op = effective_ib_operator_settings(cfg)
assert op.get('use_for_celery_bars') is True, 'use_for_celery_bars must be true'
print('  IbOperatorBarsAdapter module + use_for_celery_bars OK')
"

echo "== [5/7] Worker pod arch linux/amd64 =="
arch=$(kubectl exec -n "${NS}" deploy/celery-worker -- uname -m)
if [[ "$arch" != "x86_64" ]]; then
  echo "ERROR: celery-worker arch=${arch} (expected x86_64)" >&2
  exit 1
fi
echo "  arch ${arch} OK"

echo "== [6/7] Celery bars RPC (verify-trade-celery-bars) =="
make -C "$ROOT" verify-trade-celery-bars

echo "== [7/7] No MarketIbClient / direct ib_insync in worker bars path (source grep) =="
TASKS="${ROOT}/../bifrost-trade-worker/src/bifrost_worker/data/bars/tasks.py"
if grep -qE 'MarketIbClient|ib_insync' "$TASKS"; then
  echo "ERROR: tasks.py still references direct TWS imports" >&2
  exit 1
fi
echo "  tasks.py bars transport RPC-only OK"

echo
echo "TIBM W2 prod runtime verification OK"
