#!/usr/bin/env bash
# Switch ib-gateway mock → live via platform-api (L1). Requires TWS @ .30/.32.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
PLATFORM_API="${PLATFORM_API:-http://127.0.0.1:8780}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: Missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

TOKEN="${PLATFORM_OPERATOR_TOKEN:-${OPS_OPERATOR_TOKEN:-}}"
if [[ -z "$TOKEN" ]]; then
  echo "ERROR: PLATFORM_OPERATOR_TOKEN or OPS_OPERATOR_TOKEN required in .env" >&2
  exit 1
fi

echo "== IB Gateway mock → live =="
echo "  Probing TWS reachability (.30 / .32)..."
for ip in 192.168.10.30 192.168.10.32; do
  if nc -z -w 3 "$ip" 7496 2>/dev/null || nc -z -w 3 "$ip" 7497 2>/dev/null; then
    echo "  ${ip}: TWS port open"
  else
    echo "  WARN: ${ip}: no TWS port (7496/7497) — live switch may fail"
  fi
done

echo "== POST platform-api control/mode live =="
resp=$(curl -sf -X POST "${PLATFORM_API}/api/v1/plugins/ib-gateway/control/mode" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"mode":"live"}')
echo "$resp" | python3 -m json.tool

echo "== Waiting for ib-gateway rollout =="
kubectl rollout status deployment/ib-gateway -n data --timeout=180s

echo "== Run verify-ib-gateway-live =="
make -C "$ROOT" verify-ib-gateway-live
