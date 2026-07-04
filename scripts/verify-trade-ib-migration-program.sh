#!/usr/bin/env bash
# Trade IB Client Migration — aggregate program verification (TIBM-PC-1).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Trade IB Client Migration program verify =="
echo

echo "== [1/4] Gateway RPC parity (TIBM1) =="
make verify-ib-gateway-rpc-parity
echo

echo "== [2/4] Trade IB health (TIBM2) =="
make verify-trade-ib-health
echo

echo "== [3/4] Celery bars RPC (TIBM3) =="
make verify-trade-celery-bars
echo

echo "== [4/4] UI + ops relabel (TIBM4) =="
make verify-trade-ib-ui
echo

echo "Trade IB Client Migration program verification OK (4/4 gates)"
