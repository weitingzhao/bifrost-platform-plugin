#!/usr/bin/env bash
# TIBM Rollout W2 — build + push + rollout STG celery-worker (bars / stocks_ib data plane).
# Does NOT scale daemon (D10 BLOCKED).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STOCKS="${STOCKS_ROOT:-$(cd "$ROOT/.." && pwd)}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
REGISTRY="${STG_REGISTRY:-192.168.10.73:30500}"
TAG="${STG_TAG:-stg}"
NS="${STG_NAMESPACE:-bifrost-stg}"
WORKER_DF="${STOCKS}/bifrost-trade-infra/k8s/cicd/docker/Dockerfile.worker-stg"

need_dir() {
  if [[ ! -d "$1" ]]; then
    echo "ERROR: missing $1" >&2
    exit 1
  fi
}

for d in bifrost-trade-core bifrost-trade-worker bifrost-trade-infra; do
  need_dir "${STOCKS}/${d}"
done

push_insecure() {
  local img="$1"
  local tar="/tmp/bifrost-push-$(echo "$img" | tr '/:' '__').tar"
  if command -v crane >/dev/null 2>&1; then
    docker save "$img" -o "$tar"
    crane push --insecure "$tar" "$img"
    rm -f "$tar"
  else
    docker push "$img"
  fi
}

echo "== TIBM W2 STG rollout (celery-worker) =="
echo "Context: ${STOCKS}"
echo "Registry: ${REGISTRY}"
echo "Namespace: ${NS}"
echo

echo "== [1/2] Build bifrost-worker:${TAG} (linux/amd64) =="
docker build --platform linux/amd64 -f "$WORKER_DF" \
  -t "${REGISTRY}/bifrost-worker:${TAG}" "$STOCKS"

echo "== [2/2] Push + rollout celery-worker (daemon excluded — D10) =="
push_insecure "${REGISTRY}/bifrost-worker:${TAG}"

kubectl rollout restart "deployment/celery-worker" -n "${NS}"
kubectl rollout status "deployment/celery-worker" -n "${NS}" --timeout=300s
echo "  celery-worker OK"

echo
echo "TIBM W2 STG rollout complete — run: make verify-trade-ib-w2-stg"
