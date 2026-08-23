#!/usr/bin/env bash
# TIBM Rollout W2 — STG verify after Celery bars RETIRED (Polygon Plugin owns stock OHLC ingest).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
NS="${STG_NAMESPACE:-bifrost-stg}"

echo "== TIBM W2 STG runtime verify (Celery bars RETIRED) =="
echo

echo "== [1/4] No stocks_ib Celery worker deployment =="
if kubectl get deploy celery-worker-stocks-ib -n "${NS}" >/dev/null 2>&1; then
  replicas=$(kubectl get deploy celery-worker-stocks-ib -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
  if [[ "${replicas}" != "0" ]]; then
    echo "ERROR: celery-worker-stocks-ib replicas=${replicas} (expected retired / 0)" >&2
    exit 1
  fi
  echo "  celery-worker-stocks-ib present at replicas=0 (legacy object)"
else
  echo "  celery-worker-stocks-ib absent OK"
fi

echo "== [2/4] Daemon still scaled down (D10) =="
daemon_replicas=$(kubectl get deploy daemon -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "missing")
if [[ "$daemon_replicas" != "0" ]]; then
  echo "ERROR: daemon replicas=${daemon_replicas} (expected 0 for D10)" >&2
  exit 1
fi
echo "  daemon replicas=0 OK"

echo "== [3/4] Trade IB health (ticks / operator) =="
make -C "$ROOT" verify-trade-ib-health

echo "== [4/4] Worker package has no bars Celery module =="
WORKER_ROOT="${ROOT}/../bifrost-trade-worker/src/bifrost_worker"
if [[ -d "${WORKER_ROOT}/data/bars" ]]; then
  echo "ERROR: bifrost_worker.data.bars still present" >&2
  exit 1
fi
if [[ -d "${WORKER_ROOT}/celery" ]]; then
  echo "ERROR: bifrost_worker.celery still present" >&2
  exit 1
fi
echo "  worker Celery/bars packages removed OK"

echo
echo "TIBM W2 STG runtime verification OK (Celery bars superseded by Market Data Plugin)"
