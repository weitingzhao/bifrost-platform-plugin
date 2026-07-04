#!/usr/bin/env bash
# TIBM Rollout dev-compose — local compose W1+W2 + program verify (trade-dev ACL) + D10 guards.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INFRA="${TRADE_INFRA_ROOT:-$ROOT/../bifrost-trade-infra}"
COMPOSE=(docker compose -f "$INFRA/docker-compose.dev.yml")
MONITOR_PORT="${DEV_MONITOR_PORT:-8765}"
MIN_CORE="${TIBM_ROLLOUT_MIN_CORE:-0.2.10}"
export REDIS_IB_PORT="${REDIS_IB_PORT:-6380}"

echo "== TIBM Rollout dev-compose verify =="
echo

chmod +x "$ROOT/scripts/ensure-redis-ib-port-forward.sh"
"$ROOT/scripts/ensure-redis-ib-port-forward.sh"
echo

echo "== [1/6] config.dev.yaml — redis_ib trade-dev block =="
CFG="$INFRA/config/config.dev.yaml"
if ! grep -q '^redis_ib:' "$CFG"; then
  echo "ERROR: redis_ib block missing — run: make sync-redis-ib-dev-compose-config" >&2
  exit 1
fi
if ! grep -qE 'username: (trade-prod|trade-dev)' "$CFG"; then
  echo "ERROR: redis_ib.username must be trade-prod (RPC) or trade-dev (read-only)" >&2
  exit 1
fi
echo "  redis_ib configured OK ($(grep 'username:' "$CFG" | head -1 | xargs))"

echo "== [2/6] Program aggregate (trade-dev ACL) =="
make -C "$ROOT" verify-trade-ib-migration-program-dev

echo "== [3/6] Compose — W1 + W2 targets running =="
W1_W2=(api-monitor api-ops celery-worker frontend)
for svc in "${W1_W2[@]}"; do
  if [[ "$svc" == "frontend" ]]; then
    state=$("${COMPOSE[@]}" ps --status running --format '{{.Service}}' 2>/dev/null | grep -x "$svc" || true)
    if [[ -n "$state" ]]; then
      echo "  frontend (compose) running OK"
      continue
    fi
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "http://127.0.0.1:5173/" 2>/dev/null || echo "000")
    if [[ "$code" == "200" ]]; then
      echo "  frontend (host :5173) running OK"
      continue
    fi
    echo "  WARN: frontend not in compose (rollup optional-deps) — TIBM4 source gate covers FE; run npm run dev on host if needed"
    continue
  fi
  state=$("${COMPOSE[@]}" ps --status running --format '{{.Service}}' 2>/dev/null | grep -x "$svc" || true)
  if [[ -z "$state" ]]; then
    echo "ERROR: compose service $svc not running — run: make rollout-tibm-dev-compose" >&2
    exit 1
  fi
  echo "  $svc running OK"
done

echo "== [4/6] Legacy socket + daemon stopped (D10) =="
for svc in daemon ib-ingestor ib-account-agent ib-operator; do
  if "${COMPOSE[@]}" ps --status running --format '{{.Service}}' 2>/dev/null | grep -qx "$svc"; then
    echo "ERROR: $svc must not run during dev-compose rollout (use Platform Gateway only)" >&2
    exit 1
  fi
  echo "  $svc not running OK"
done

echo "== [5/6] Local runtime — core + monitor /status =="
for svc in api-monitor api-ops celery-worker; do
  "${COMPOSE[@]}" exec -T "$svc" python -c "
import importlib.metadata as m
v = m.version('bifrost-core')
min_v = '${MIN_CORE}'.split('.')
cur = v.split('.')
for i in range(max(len(min_v), len(cur))):
    a = int(cur[i]) if i < len(cur) else 0
    b = int(min_v[i]) if i < len(min_v) else 0
    if a > b:
        break
    if a < b:
        raise SystemExit(f'ERROR: ${svc} bifrost-core {v} < ${MIN_CORE}')
print(f'  ${svc} bifrost-core {v} OK')
"
done

"${COMPOSE[@]}" exec -T celery-worker python -c "
import importlib.util
assert importlib.util.find_spec('bifrost_worker.data.bars.ib_operator_transport'), 'missing ib_operator_transport'
print('  celery-worker IbOperatorBarsAdapter OK')
"

status_json=$(curl -sf "http://127.0.0.1:${MONITOR_PORT}/status")
python3 -c "
import json, sys
d = json.loads(sys.argv[1])
assert d.get('socket', {}).get('platform_ib_gateway') is not None, 'platform_ib_gateway missing'
print('  local Monitor /status platform_ib_gateway OK')
" "$status_json"

echo "== [6/6] Dev stack health subset =="
check_http() {
  local name="$1" url="$2"
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" 2>/dev/null || echo "000")
  if [[ "$code" != "200" && "$code" != "503" ]]; then
    echo "ERROR: $name $url ($code)" >&2
    exit 1
  fi
  echo "  $name HTTP $code OK"
}
check_http "api-monitor" "http://127.0.0.1:${MONITOR_PORT}/status"
check_http "api-ops" "http://127.0.0.1:8768/health"
fe_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "http://127.0.0.1:5173/" 2>/dev/null || echo "000")
if [[ "$fe_code" == "200" ]]; then
  echo "  frontend HTTP 200 OK"
else
  echo "  WARN: frontend :5173 not up — optional for dev-compose gate (TIBM4 source OK)"
fi

echo
echo "TIBM Rollout dev-compose verification OK"
