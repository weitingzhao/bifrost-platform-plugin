#!/usr/bin/env bash
# Trade IB Client Migration — dev-compose program gate (trade-dev read + trade-prod RPC program).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Trade IB Client Migration program verify (dev-compose) =="
echo

echo "== [1/2] trade-dev read ACL (dev redis-ib alias) =="
make verify-trade-ib-dev-read
echo

echo "== [2/2] Full program verify (trade-prod RPC — celery/operator write path) =="
make verify-trade-ib-migration-program
echo

echo "Trade IB Client Migration dev-compose program verification OK"
