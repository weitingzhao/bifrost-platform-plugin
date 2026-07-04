#!/usr/bin/env bash
# IBGP3 — verify Trade cutover: legacy IB socket retired, Trade reads Platform redis-ib bus.
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

LEGACY_STS=(ib-market-gateway ib-account-agent ib-operator)
TRADE_NS=(bifrost-dev bifrost-stg bifrost-prod)

echo "== [1/5] Legacy IB StatefulSets scaled to 0 =="
for NS in "${TRADE_NS[@]}"; do
  for sts in "${LEGACY_STS[@]}"; do
    reps="$(kubectl get "statefulset/${sts}" -n "$NS" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo missing)"
    if [[ "$reps" == "missing" ]]; then
      echo "  $NS/$sts — absent (OK)"
    elif [[ "$reps" == "0" ]]; then
      echo "  $NS/$sts — replicas=0 OK"
    else
      echo "FAIL $NS/$sts still replicas=$reps" >&2
      exit 1
    fi
  done
done

echo "== [2/5] ExternalName redis-ib in Trade NS =="
for NS in "${TRADE_NS[@]}"; do
  kubectl get svc redis-ib -n "$NS" >/dev/null
  echo "  $NS/redis-ib OK"
done

echo "== [3/5] Platform ib-gateway @ data NS =="
kubectl get deploy/ib-gateway -n data -o jsonpath='{.status.readyReplicas}/{.spec.replicas} ready' && echo
kubectl wait --for=condition=available deployment/ib-gateway -n data --timeout=60s

echo "== [4/5] Trade ACL ping + tick read (via api-market — bypasses NetworkPolicy) =="
for NS in "${TRADE_NS[@]}"; do
  kubectl exec -n "$NS" deploy/api-market -- python3 -c "
import os, yaml, redis
cfg_path = os.environ.get('BIFROST_CONFIG', '/app/config/config.stg.yaml')
with open(cfg_path) as f:
    cfg = yaml.safe_load(f)
rb = cfg.get('redis_ib') or {}
r = redis.Redis(
    host=rb.get('host') or 'redis-ib',
    port=int(rb.get('port') or 6379),
    username=rb.get('username'),
    password=rb.get('password'),
    db=int(rb.get('db') or 0),
    decode_responses=True,
    socket_connect_timeout=5,
)
assert r.ping(), 'ping failed'
val = r.get('ib:ingester:tick:NVDA|STK|||')
assert val, 'missing NVDA tick'
print(rb.get('username') or 'unknown')
" >/tmp/cutover-user-"$$".txt || { echo "FAIL ACL/tick $NS" >&2; exit 1; }
  USER=$(tr -d '\r\n' </tmp/cutover-user-"$$".txt)
  rm -f /tmp/cutover-user-"$$".txt
  echo "  $NS ($USER) OK"
done

echo "== [5/5] Operator RPC via trade-prod ACL =="
# shellcheck disable=SC1091
source "$(dirname "$0")/lib/redis_operator_ping.sh"
REQ_ID="cutover-verify-$$"
RESULT=$(redis_operator_ping "redis://trade-prod:${REDIS_IB_TRADE_PROD_PASS}@127.0.0.1:6379" "$REQ_ID" 15)
echo "$RESULT" | head -c 120
echo
echo "  operator ping OK"

echo "IBGP3 Trade cutover verification OK"
