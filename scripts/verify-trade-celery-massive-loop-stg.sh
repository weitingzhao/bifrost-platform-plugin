#!/usr/bin/env bash
# trade-celery-k8s-ideal W1/W3 — verify STG Celery Massive loop hemostasis.
# Checks: worker -Q / active_queues, beat Running, stocks_ib present, daemon replicas=0.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
NS="${BIFROST_TRADE_NS:-bifrost-stg}"

pass() { echo "  PASS: $*"; }
fail() { echo "  FAIL: $*" >&2; exit 1; }

echo "== Trade Celery / Massive STG loop verify (ns=${NS}) =="

echo "== [1/6] Deployments present =="
kubectl get deploy -n "$NS" celery-worker celery-beat flower daemon --no-headers

echo "== [2/6] daemon replicas=0 (D10) =="
DAEMON_REP="$(kubectl get deploy daemon -n "$NS" -o jsonpath='{.spec.replicas}')"
[[ "${DAEMON_REP}" == "0" ]] || fail "daemon replicas=${DAEMON_REP} (expected 0 — D10 BLOCKED)"
pass "daemon replicas=0"

echo "== [3/6] celery-beat Ready =="
kubectl wait --for=condition=available deploy/celery-beat -n "$NS" --timeout=120s
BEAT_READY="$(kubectl get deploy celery-beat -n "$NS" -o jsonpath='{.status.readyReplicas}')"
[[ "${BEAT_READY}" == "1" ]] || fail "celery-beat readyReplicas=${BEAT_READY}"
pass "celery-beat 1/1"

echo "== [4/6] celery workers Ready =="
# W1 monolith or W3 profile Deployments
if kubectl get deploy -n "$NS" -o name 2>/dev/null | grep -q 'celery-worker-'; then
  for d in celery-worker-stocks-ib celery-worker-stocks-massive celery-worker-options-massive; do
    kubectl wait --for=condition=available "deploy/${d}" -n "$NS" --timeout=180s
  done
  pass "profile celery-worker-* base Deployments Available"
  # Monolith should be scaled to 0 under W3
  MONO_REP="$(kubectl get deploy celery-worker -n "$NS" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)"
  if [[ "${MONO_REP}" != "0" && -n "${MONO_REP}" ]]; then
    echo "  WARN: monolith celery-worker replicas=${MONO_REP} (prefer 0 under W3 to avoid double-consume)"
  else
    pass "monolith celery-worker replicas=0"
  fi
else
  kubectl wait --for=condition=available deploy/celery-worker -n "$NS" --timeout=180s
  pass "celery-worker Available"
fi

echo "== [5/6] Worker command uses systemd entry OR -Q =="
CMD="$(kubectl get deploy celery-worker -n "$NS" -o jsonpath='{.spec.template.spec.containers[0].command}')"
echo "  command=${CMD}"
if echo "${CMD}" | grep -q 'systemd/run_celery.py'; then
  pass "uses scripts/systemd/run_celery.py"
elif echo "${CMD}" | grep -q '\-Q'; then
  pass "explicit -Q in command"
else
  # Per-queue Deployments (W3) use --instance on systemd entry
  if kubectl get deploy -n "$NS" -o name 2>/dev/null | grep -q 'celery-worker-'; then
    pass "per-queue celery-worker-* Deployments present (W3)"
  else
    fail "celery-worker command does not look like all-queues entry: ${CMD}"
  fi
fi

echo "== [6/6] active_queues include Massive + stocks_ib =="
# Prefer monolithic celery-worker; fall back to any celery-worker-* pod
POD="$(kubectl get pods -n "$NS" -l app.kubernetes.io/name=celery-worker -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "${POD}" ]]; then
  POD="$(kubectl get pods -n "$NS" --no-headers 2>/dev/null | awk '/celery-worker/{print $1; exit}')"
fi
[[ -n "${POD}" ]] || fail "no celery-worker pod found"
QUEUES_OUT="$(kubectl exec -n "$NS" "$POD" -- celery -A bifrost_worker.celery.celery_app inspect active_queues 2>/dev/null || true)"
echo "${QUEUES_OUT}" | head -80
echo "${QUEUES_OUT}" | grep -q "stocks_ib" || fail "stocks_ib not in active_queues"
# Massive: either this pod consumes them (W1 all-queues) or sibling profile pods do (W3)
if echo "${QUEUES_OUT}" | grep -qE "options_massive|stocks_massive"; then
  pass "Massive queue(s) present on inspected worker"
else
  # W3: check union across pods
  FOUND_MASSIVE=0
  for p in $(kubectl get pods -n "$NS" --no-headers 2>/dev/null | awk '/celery-worker/{print $1}'); do
    qo="$(kubectl exec -n "$NS" "$p" -- celery -A bifrost_worker.celery.celery_app inspect active_queues 2>/dev/null || true)"
    if echo "${qo}" | grep -qE "options_massive|stocks_massive"; then
      FOUND_MASSIVE=1
      break
    fi
  done
  [[ "${FOUND_MASSIVE}" == "1" ]] || fail "no worker consumes Massive queues"
  pass "Massive queue(s) present across celery-worker pods (W3)"
fi
pass "stocks_ib present"

echo
echo "Trade Celery / Massive STG loop verify OK"
echo "  (flower: kubectl -n ${NS} get deploy flower)"
echo "  (D10: daemon stays replicas=0 — do not scale for live trade)"
