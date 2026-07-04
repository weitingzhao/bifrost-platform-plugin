#!/usr/bin/env bash
# Sync redis_ib block into bifrost-trade-infra config.dev.yaml for local compose (trade-dev ACL).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
INFRA_CFG="${TRADE_INFRA_CONFIG:-$ROOT/../bifrost-trade-infra/config/config.dev.yaml}"
REDIS_IB_HOST="${REDIS_IB_HOST:-host.docker.internal}"
REDIS_IB_PORT="${REDIS_IB_PORT:-6380}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

if [[ ! -f "$INFRA_CFG" ]]; then
  echo "ERROR: missing $INFRA_CFG" >&2
  exit 1
fi

PASS="${REDIS_IB_TRADE_DEV_PASS:?REDIS_IB_TRADE_DEV_PASS missing}"
# Celery bars + operator RPC require write ACL — use trade-prod locally (trade-dev is read-only).
REDIS_IB_USER="${REDIS_IB_COMPOSE_USER:-trade-prod}"
if [[ "$REDIS_IB_USER" == "trade-prod" ]]; then
  PASS="${REDIS_IB_TRADE_PROD_PASS:?REDIS_IB_TRADE_PROD_PASS missing}"
fi

python3 - "$INFRA_CFG" "$REDIS_IB_HOST" "$REDIS_IB_PORT" "$REDIS_IB_USER" "$PASS" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
host = sys.argv[2]
port = sys.argv[3]
username = sys.argv[4]
password = sys.argv[5]
text = path.read_text(encoding="utf-8")

block = f"""redis_ib:
  enabled: true
  host: {host}
  port: {port}
  db: 0
  username: {username}
  password: "{password}"
"""

if re.search(r"^redis_ib:\n", text, re.MULTILINE):
    out, n = re.subn(r"^redis_ib:\n(?:  .+\n)+", block, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"failed to replace redis_ib block in {path}")
else:
    anchor = re.search(r"^redis:\n(?:  .+\n)+", text, re.MULTILINE)
    if not anchor:
        raise SystemExit(f"redis: block not found in {path}")
    insert_at = anchor.end()
    out = text[:insert_at] + "\n" + block + text[insert_at:]

path.write_text(out, encoding="utf-8")
print(f"Updated {path} redis_ib → {username} @ {host}:{port}")
PY

echo "Hint: ensure redis-ib reachable from compose — e.g. kubectl port-forward -n data svc/redis-ib ${REDIS_IB_PORT}:6379"
