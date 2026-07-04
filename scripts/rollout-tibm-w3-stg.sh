#!/usr/bin/env bash
# TIBM Rollout W3 — build + push + rollout STG read-only API domains.
# Does NOT scale daemon (D10 BLOCKED). api-strategy excluded from W3 scope.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STOCKS="${STOCKS_ROOT:-$(cd "$ROOT/.." && pwd)}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
REGISTRY="${STG_REGISTRY:-192.168.10.73:30500}"
TAG="${STG_TAG:-stg}"
NS="${STG_NAMESPACE:-bifrost-stg}"
API_DF="${STOCKS}/bifrost-trade-infra/k8s/cicd/docker/Dockerfile.api-stg"

W3_API_IMAGES=(
  bifrost-api-market
  bifrost-api-massive
  bifrost-api-research
  bifrost-api-portfolio
  bifrost-api-docs
  bifrost-api-trading
)

W3_DEPLOYMENTS=(
  api-market
  api-massive
  api-research
  api-portfolio
  api-docs
  api-trading
)

need_dir() {
  if [[ ! -d "$1" ]]; then
    echo "ERROR: missing $1" >&2
    exit 1
  fi
}

for d in bifrost-trade-core bifrost-trade-worker bifrost-trade-socket bifrost-trade-api bifrost-trade-infra; do
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

echo "== TIBM W3 STG rollout (read-only API domains) =="
echo "Context: ${STOCKS}"
echo "Registry: ${REGISTRY}"
echo "Namespace: ${NS}"
echo

echo "== [1/3] Build shared API base (linux/amd64, API_DOMAIN=market) =="
docker build --platform linux/amd64 -f "$API_DF" --build-arg API_DOMAIN=market \
  -t "${REGISTRY}/bifrost-api-market:${TAG}" "$STOCKS"

echo "== [2/3] Tag + push W3 API images =="
for img in "${W3_API_IMAGES[@]}"; do
  if [[ "$img" != "bifrost-api-market" ]]; then
    docker tag "${REGISTRY}/bifrost-api-market:${TAG}" "${REGISTRY}/${img}:${TAG}"
  fi
  push_insecure "${REGISTRY}/${img}:${TAG}"
  echo "  pushed ${img}:${TAG}"
done

echo "== [3/3] Rollout restart W3 deployments (daemon excluded — D10) =="
for dep in "${W3_DEPLOYMENTS[@]}"; do
  kubectl rollout restart "deployment/${dep}" -n "${NS}"
  kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=300s
  echo "  ${dep} OK"
done

echo
echo "TIBM W3 STG rollout complete — run: make verify-trade-ib-w3-stg"
