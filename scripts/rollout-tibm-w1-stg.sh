#!/usr/bin/env bash
# TIBM Rollout W1 — build + push + rollout STG observability plane (monitor, ops, frontend).
# Does NOT scale daemon (D10 BLOCKED).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STOCKS="${STOCKS_ROOT:-$(cd "$ROOT/.." && pwd)}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
REGISTRY="${STG_REGISTRY:-192.168.10.73:30500}"
TAG="${STG_TAG:-stg}"
NS="${STG_NAMESPACE:-bifrost-stg}"
API_DF="${STOCKS}/bifrost-trade-infra/k8s/cicd/docker/Dockerfile.api-stg"
FE_DF="${STOCKS}/bifrost-trade-infra/k8s/cicd/docker/Dockerfile.frontend-stg"

need_dir() {
  if [[ ! -d "$1" ]]; then
    echo "ERROR: missing $1" >&2
    exit 1
  fi
}

for d in bifrost-trade-core bifrost-trade-worker bifrost-trade-socket bifrost-trade-api bifrost-trade-frontend bifrost-ui bifrost-trade-infra; do
  need_dir "${STOCKS}/${d}"
done

echo "== TIBM W1 STG rollout =="
echo "Context: ${STOCKS}"
echo "Registry: ${REGISTRY}"
echo "Namespace: ${NS}"
echo

echo "== [1/4] Build api-monitor:${TAG} (shared API base, linux/amd64) =="
docker build --platform linux/amd64 -f "$API_DF" --build-arg API_DOMAIN=monitor \
  -t "${REGISTRY}/bifrost-api-monitor:${TAG}" "$STOCKS"

echo "== [2/4] Tag api-ops + push API images =="
docker tag "${REGISTRY}/bifrost-api-monitor:${TAG}" "${REGISTRY}/bifrost-api-ops:${TAG}"
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
push_insecure "${REGISTRY}/bifrost-api-monitor:${TAG}"
push_insecure "${REGISTRY}/bifrost-api-ops:${TAG}"

echo "== [3/4] Build + push frontend:${TAG} (linux/amd64) =="
FE_DF_DIST="${STOCKS}/bifrost-trade-infra/k8s/cicd/docker/Dockerfile.frontend-stg-dist"
if [[ -f "${STOCKS}/bifrost-trade-frontend/dist/index.html" ]]; then
  echo "  Using prebuilt dist (Dockerfile.frontend-stg-dist) — run vite build locally if FE changed"
  docker build --platform linux/amd64 -f "$FE_DF_DIST" -t "${REGISTRY}/bifrost-frontend:${TAG}" "$STOCKS"
else
  docker build --platform linux/amd64 -f "$FE_DF" -t "${REGISTRY}/bifrost-frontend:${TAG}" "$STOCKS"
fi
push_insecure "${REGISTRY}/bifrost-frontend:${TAG}"

echo "== [4/4] Rollout restart W1 deployments (daemon excluded — D10) =="
for dep in api-monitor api-ops frontend; do
  kubectl rollout restart "deployment/${dep}" -n "${NS}"
  kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=300s
  echo "  ${dep} OK"
done

echo
echo "TIBM W1 STG rollout complete — run: make verify-trade-ib-w1-stg"
