#!/usr/bin/env bash
# Print the redis-ib ACL file: acl.conf.example with passwords from .env, comments and blank lines
# dropped (Redis rejects comments in an ACL file). Output holds passwords — pipe it, never log it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy .env.example and set passwords." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

for var in REDIS_IB_GATEWAY_PASS REDIS_IB_TRADE_PROD_PASS REDIS_IB_TRADE_DEV_PASS REDIS_IB_TRADE_STG_PASS REDIS_IB_PLATFORM_PASS; do
  if [[ -z "${!var:-}" || "${!var}" == change-me-* ]]; then
    echo "Set $var in $ENV_FILE first (scripts/redis-ib-env-users.sh acl creates the Trade env ones)." >&2
    exit 1
  fi
done

sed \
  -e "s|>GATEWAY_PASS|>${REDIS_IB_GATEWAY_PASS}|g" \
  -e "s|>TRADE_PROD_PASS|>${REDIS_IB_TRADE_PROD_PASS}|g" \
  -e "s|>TRADE_DEV_PASS|>${REDIS_IB_TRADE_DEV_PASS}|g" \
  -e "s|>TRADE_STG_PASS|>${REDIS_IB_TRADE_STG_PASS}|g" \
  -e "s|>PLATFORM_PASS|>${REDIS_IB_PLATFORM_PASS}|g" \
  -e '/^[[:space:]]*#/d' \
  -e '/^[[:space:]]*$/d' \
  "$ROOT/k8s/redis-ib/acl.conf.example"
