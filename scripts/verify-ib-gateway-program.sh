#!/usr/bin/env bash
# IB Gateway Plugin — full program verification (post IBGP4 sign-off).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM_API="${PLATFORM_API:-http://127.0.0.1:8780}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"

echo "== [1/3] Trade cutover (IBGP3) =="
make -C "$ROOT" verify-trade-cutover

echo ""
echo "== [2/3] Live TWS (IBGP4) =="
make -C "$ROOT" verify-ib-gateway-live

echo ""
echo "== [3/3] Program status aggregate =="
curl -sS "${PLATFORM_API}/api/v1/plugins/ib-gateway/status" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('mode') == 'live', f\"mode={d.get('mode')}\"
assert d.get('reachability') in ('ok', 'degraded'), d.get('reachability')
slots = d.get('slots') or []
assert len(slots) >= 2
for s in slots:
    assert s.get('connected') is True, s
c = d.get('cutover') or {}
assert c.get('legacy_socket_retired') is True, c
for e in c.get('environments') or []:
    assert e.get('legacy_ib_replicas') == 0, e
    assert e.get('redis_ib_external_name_ok') is True, e
print('  mode=live slots connected cutover retired all envs OK')
"

echo "IB Gateway Plugin program verification OK"
