#!/usr/bin/env bash
# TIBM post-rollout — api-strategy core alignment (STG + PROD). D10 still blocks live trading.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STOCKS="${STOCKS_ROOT:-$(cd "$ROOT/.." && pwd)}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
REGISTRY="${TIBM_REGISTRY:-192.168.10.73:30500}"
API_DF="${STOCKS}/bifrost-trade-infra/k8s/cicd/docker/Dockerfile.api-stg"

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

rollout_env() {
  local tag="$1"
  local ns="$2"
  echo "== Rollout api-strategy:${tag} in ${ns} =="
  kubectl rollout restart "deployment/api-strategy" -n "${ns}"
  kubectl rollout status "deployment/api-strategy" -n "${ns}" --timeout=300s
  kubectl exec -n "${ns}" deploy/api-strategy -- python -c \
    "import importlib.metadata as m; print('  bifrost-core', m.version('bifrost-core'))"
}

echo "== TIBM api-strategy rollout (STG + PROD) =="
echo "Registry: ${REGISTRY}"
echo

echo "== [1/3] Build bifrost-api-strategy:stg (linux/amd64) =="
docker build --platform linux/amd64 -f "$API_DF" --build-arg API_DOMAIN=strategy \
  -t "${REGISTRY}/bifrost-api-strategy:stg" "$STOCKS"

echo "== [2/3] Tag :prod + push =="
docker tag "${REGISTRY}/bifrost-api-strategy:stg" "${REGISTRY}/bifrost-api-strategy:prod"
push_insecure "${REGISTRY}/bifrost-api-strategy:stg"
push_insecure "${REGISTRY}/bifrost-api-strategy:prod"

echo "== [3/3] Rollout restart =="
rollout_env stg bifrost-stg
rollout_env prod bifrost-prod

echo
echo "TIBM api-strategy rollout complete — run: make verify-tibm-strategy-alignment"
