#!/usr/bin/env bash
# TIBM Rollout dev-compose — sync redis_ib config + restart W1/W2 compose targets (no daemon / legacy socket).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INFRA="${TRADE_INFRA_ROOT:-$ROOT/../bifrost-trade-infra}"
COMPOSE=(docker compose -f "$INFRA/docker-compose.dev.yml")

echo "== TIBM dev-compose rollout =="
echo

echo "== [1/5] Sync dev overlay (postgres/redis/ib from .env) =="
make -C "$INFRA" sync-dev-config

echo "== [2/5] Sync redis_ib into config.dev.yaml =="
chmod +x "$ROOT/scripts/sync-redis-ib-dev-compose-config.sh" "$ROOT/scripts/ensure-redis-ib-port-forward.sh"
export REDIS_IB_PORT="${REDIS_IB_PORT:-6380}"
"$ROOT/scripts/ensure-redis-ib-port-forward.sh"
"$ROOT/scripts/sync-redis-ib-dev-compose-config.sh"

echo "== [3/5] Stop daemon + legacy IB socket services (D10 / IBGP3) =="
"${COMPOSE[@]}" stop daemon ib-ingestor ib-account-agent ib-operator 2>/dev/null || true

echo "== [4/5] Refresh editable installs (bifrost-core >= 0.2.10) =="
make -C "$INFRA" dev-reinstall-deps

echo "== [5/5] Start W1 + W2 compose targets =="
"${COMPOSE[@]}" up -d api-monitor api-ops celery-worker frontend

echo "== [6/6] Ensure bifrost-core editable @ workspace (>= 0.2.10) =="
for svc in api-monitor api-ops celery-worker; do
  "${COMPOSE[@]}" exec -T "$svc" pip install -e /workspace/bifrost-trade-core -q
  echo "  ${svc} bifrost-core reinstalled"
done
"${COMPOSE[@]}" restart api-monitor api-ops celery-worker

echo
echo "TIBM dev-compose rollout complete — wait ~90s for APIs, then: make verify-trade-ib-rollout-dev-compose"
echo "redis-ib forwarded to host :${REDIS_IB_PORT:-6380} (compose redis_ib host.docker.internal:${REDIS_IB_PORT:-6380})"
