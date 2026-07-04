#!/usr/bin/env bash
# Verify redis-ib on K3s — ACL + ExternalName (Phase 0 step 2).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

echo "== redis-ib resources =="
kubectl get pods,svc,pdb -n data -l app.kubernetes.io/name=redis-ib
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=redis-ib -n data --timeout=30s

echo "== ACL smoke (in-cluster) =="
kubectl exec -n data deploy/redis-ib -- redis-cli -u "redis://trade-dev:${REDIS_IB_TRADE_DEV_PASS}@127.0.0.1:6379" PING
kubectl exec -n data deploy/redis-ib -- redis-cli -u "redis://trade-prod:${REDIS_IB_TRADE_PROD_PASS}@127.0.0.1:6379" PING

echo "== ExternalName services =="
for NS in bifrost-dev bifrost-stg bifrost-prod; do
  kubectl get svc redis-ib -n "$NS"
done

echo "== bifrost-prod → redis-ib PING =="
kubectl run "redis-ib-verify-$$" -n bifrost-prod --rm -i --restart=Never --image=redis:7-alpine --command -- sh -c \
  "nc -z redis-ib 6379 && redis-cli -h redis-ib -p 6379 --user trade-prod --pass '${REDIS_IB_TRADE_PROD_PASS}' PING"

echo "redis-ib verification OK"
