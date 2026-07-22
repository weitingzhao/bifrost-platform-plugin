#!/usr/bin/env bash
# TIBM Rollout W3 — runtime verify STG read-only API domains after image rollout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
NS="${STG_NAMESPACE:-bifrost-stg}"
# Traefik NodePort escape hatch (trade-gateway-ip :30880) — no Host header.
# VIP alt: STG_TRADE_BASE_URL=https://192.168.10.100 STG_TRADE_HOST=stg.trader.bifrost.lan
STG_BASE_URL="${STG_TRADE_BASE_URL:-http://192.168.10.73:30880}"
STG_HOST="${STG_TRADE_HOST:-}"
MIN_CORE_VERSION="${TIBM_W3_MIN_CORE_VERSION:-0.2.10}"

stg_curl() {
  if [[ -n "${STG_HOST}" ]]; then
    curl -sf -H "Host: ${STG_HOST}" "$@"
  else
    curl -sf "$@"
  fi
}

W3_DEPLOYMENTS=(
  api-market
  api-massive
  api-research
  api-portfolio
  api-docs
  api-trading
)

echo "== TIBM W3 STG runtime verify =="
echo

echo "== [1/6] W3 API deployments ready =="
for dep in "${W3_DEPLOYMENTS[@]}"; do
  kubectl wait --for=condition=available "deployment/${dep}" -n "${NS}" --timeout=120s
  echo "  ${dep} available"
done

echo "== [2/6] Daemon still scaled down (D10) =="
daemon_replicas=$(kubectl get deploy daemon -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "missing")
if [[ "$daemon_replicas" != "0" ]]; then
  echo "ERROR: daemon replicas=${daemon_replicas} (expected 0 for D10)" >&2
  exit 1
fi
echo "  daemon replicas=0 OK"

echo "== [3/6] bifrost-core >= ${MIN_CORE_VERSION} on all W3 API pods =="
for dep in "${W3_DEPLOYMENTS[@]}"; do
  kubectl exec -n "${NS}" "deploy/${dep}" -- python -c "
import importlib.metadata as m
v = m.version('bifrost-core')
min_v = '${MIN_CORE_VERSION}'.split('.')
cur = v.split('.')
for i in range(max(len(min_v), len(cur))):
    a = int(cur[i]) if i < len(cur) else 0
    b = int(min_v[i]) if i < len(min_v) else 0
    if a > b:
        break
    if a < b:
        raise SystemExit(f'ERROR: ${dep} bifrost-core {v} < ${MIN_CORE_VERSION}')
print(f'  ${dep} bifrost-core {v} OK')
"
done

echo "== [4/6] Ingress GET /health — all W3 domains =="
for path in \
  "/api/market/health" \
  "/api/massive/health" \
  "/api/research/health" \
  "/api/portfolio/health" \
  "/api/docs/health" \
  "/api/trading/health"; do
  code=$(stg_curl -o /dev/null -w "%{http_code}" "${STG_BASE_URL}${path}" || echo "000")
  if [[ "$code" != "200" ]]; then
    echo "ERROR: ${path} HTTP ${code} (expected 200)" >&2
    exit 1
  fi
  echo "  ${path} HTTP 200"
done

echo "== [5/6] Trading read-only smoke (GET /executions/freshness) =="
fresh_code=$(stg_curl -o /dev/null -w "%{http_code}" \
  "${STG_BASE_URL}/api/trading/executions/freshness" || echo "000")
if [[ "$fresh_code" != "200" ]]; then
  echo "ERROR: /api/trading/executions/freshness HTTP ${fresh_code}" >&2
  exit 1
fi
echo "  /api/trading/executions/freshness HTTP 200"

echo "== [6/6] Market quotes smoke (redis-ib + GET /quotes) =="
quotes_json=$(stg_curl "${STG_BASE_URL}/api/market/quotes?symbols=NVDA" || true)
if [[ -z "$quotes_json" ]]; then
  echo "ERROR: GET /api/market/quotes failed" >&2
  exit 1
fi
python3 -c "
import json, sys
d = json.loads(sys.argv[1])
assert 'quotes' in d, 'missing quotes key'
if d.get('message') == 'Real-time quotes disabled or Redis unavailable':
    raise SystemExit('ERROR: Market API redis_quotes unavailable — check redis-live-stg + redis_ib config')
print('  GET /api/market/quotes OK (quotes len=%d)' % len(d.get('quotes') or []))
" "$quotes_json"

kubectl exec -n "${NS}" deploy/api-market -- python -c "
import yaml, os, redis
from bifrost_core.core.redis_url import ib_redis_url_from_config
with open(os.environ['BIFROST_CONFIG']) as f:
    cfg = yaml.safe_load(f)
url = ib_redis_url_from_config(cfg)
r = redis.from_url(url, decode_responses=True, socket_connect_timeout=3)
assert r.ping(), 'redis_ib ping failed'
print('  api-market → redis_ib PING OK')
" 2>&1

if [[ -f "${ROOT}/.env" ]]; then
  # shellcheck disable=SC1090
  source "${ROOT}/.env"
  tick=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u \
    "redis://trade-prod:${REDIS_IB_TRADE_PROD_PASS}@127.0.0.1:6379" \
    --no-auth-warning GET "ib:ingester:tick:NVDA|STK|||" 2>/dev/null || true)
  if [[ -n "$tick" && "$tick" == *"contract_key"* ]]; then
    echo "  redis-ib NVDA tick key present"
    make -C "$ROOT" verify-trade-quotes-e2e
  else
    echo "  WARN: no ib:ingester:tick on redis-ib (Gateway mock / no live ingest) — skip full quotes E2E"
    echo "  W3 gate: Market API read path + redis_ib OK; live tick optional until Gateway live"
  fi
else
  echo "  WARN: ${ROOT}/.env missing — skip redis-ib tick probe"
fi

echo
echo "TIBM W3 STG runtime verification OK"
