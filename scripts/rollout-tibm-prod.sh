#!/usr/bin/env bash
# TIBM Rollout prod — promote W1→W3 to bifrost-prod (observe + data path only).
# Does NOT enable live trading (D10 BLOCKED); daemon observe-safe patch unchanged.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$(dirname "$0")/lib/tibm_prod_defaults.sh"

echo "== TIBM Rollout prod (W1→W3) =="
echo "Registry: ${PROD_REGISTRY}"
echo "Tag: ${PROD_TAG}"
echo "Namespace: ${PROD_NAMESPACE}"
echo

run_wave() {
  local script="$1"
  STG_REGISTRY="${PROD_REGISTRY}" \
  STG_TAG="${PROD_TAG}" \
  STG_NAMESPACE="${PROD_NAMESPACE}" \
  "$ROOT/scripts/${script}"
}

chmod +x "$ROOT/scripts/rollout-tibm-w1-stg.sh" \
  "$ROOT/scripts/rollout-tibm-w2-stg.sh" \
  "$ROOT/scripts/rollout-tibm-w3-stg.sh"

echo "== [1/3] W1 observability =="
run_wave rollout-tibm-w1-stg.sh

echo "== [2/3] W2 data plane =="
run_wave rollout-tibm-w2-stg.sh

echo "== [3/3] W3 read-only APIs =="
run_wave rollout-tibm-w3-stg.sh

echo
echo "TIBM Rollout prod (W1→W3) complete — run: make verify-trade-ib-rollout-prod"
