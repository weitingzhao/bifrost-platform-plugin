#!/usr/bin/env bash
# Sync redis-ib ACL passwords: plugin .env → Trade overlay configs + platform .env
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRADE_INFRA="${TRADE_INFRA:-$ROOT/../bifrost-trade-infra}"
PLATFORM="${PLATFORM:-$ROOT/../bifrost-platform}"
PLUGIN_ENV="${PLUGIN_ENV:-$ROOT/.env}"

if [[ ! -f "$PLUGIN_ENV" ]]; then
  echo "Missing $PLUGIN_ENV" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$PLUGIN_ENV"

DEV_PASS="${REDIS_IB_TRADE_DEV_PASS:?}"
PROD_PASS="${REDIS_IB_TRADE_PROD_PASS:?}"
PLATFORM_PASS="${REDIS_IB_PLATFORM_PASS:?}"

echo "== Trade overlay configs =="
TRADE_INFRA="$TRADE_INFRA" PLUGIN_ENV="$PLUGIN_ENV" "$TRADE_INFRA/scripts/sync_redis_ib_trade_config.sh"

echo ""
echo "== Platform .env REDIS_IB_PLATFORM_PASS =="
PLATFORM_ENV="$PLATFORM/.env"
if [[ ! -f "$PLATFORM_ENV" ]]; then
  echo "SKIP $PLATFORM_ENV not found" >&2
else
  python3 - "$PLATFORM_ENV" "$PLATFORM_PASS" <<'PY'
import re, sys
from pathlib import Path
path, pw = Path(sys.argv[1]), sys.argv[2]
text = path.read_text(encoding="utf-8")
if re.search(r"^REDIS_IB_PLATFORM_PASS=", text, flags=re.MULTILINE):
    text = re.sub(r"^REDIS_IB_PLATFORM_PASS=.*$", f"REDIS_IB_PLATFORM_PASS={pw}", text, count=1, flags=re.MULTILINE)
else:
    text = text.rstrip() + f"\nREDIS_IB_PLATFORM_PASS={pw}\n"
path.write_text(text, encoding="utf-8")
print(f"Updated {path} REDIS_IB_PLATFORM_PASS")
PY
fi

echo "redis-ib secrets synced (plugin → trade overlays + platform .env)"
