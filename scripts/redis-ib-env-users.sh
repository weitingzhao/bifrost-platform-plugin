#!/usr/bin/env bash
# Trade DEV and STG each on their own redis-ib user instead of trade-prod (debt TD-21).
# Run by the Owner: every step that handles a password is in here, and none of them prints one.
# Passwords live only in this repo's .env, Secret data/redis-ib-acl and Secret bifrost-<env>-secrets.
#
#   acl [--rotate-dev]  Put REDIS_IB_TRADE_STG_PASS in .env if it is missing (and a fresh
#                       REDIS_IB_TRADE_DEV_PASS with --rotate-dev), update Secret redis-ib-acl, wait
#                       until the redis-ib pod sees the new file, then ACL LOAD. Connections stay up;
#                       a file Redis rejects leaves the old users in force.
#   switch dev|stg      Point bifrost-<env>-secrets at trade-<env> and restart that env's Trade pods.
#                       Refuses unless the env's config already sends RPCs to its own operator stream.
#   rollback dev|stg    Point it back at trade-prod and restart.
#   check [minutes]     Connections per user, and what redis-ib refused trade-dev / trade-stg in the
#                       last N minutes (default 60). Never prints a secret.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
TRADE_INFRA="${TRADE_INFRA:-$ROOT/../bifrost-trade-infra}"
# W-33 LANE-W33D: gateway and trade-prod passwords, and the Trade Secret files,
# moved to the Owner's directory. Owner-only script; the Agent gate refuses it.
OWNER_DIR="${BIFROST_OWNER_DIR:-$HOME/.bifrost-owner}"
OWNER_ENV="${BIFROST_OWNER_ENV:-$OWNER_DIR/owner.env}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
# Trade Deployments that read REDIS_IB_* from bifrost-<env>-secrets.
TRADE_DEPLOYS=(api-account api-market api-monitor api-research daemon)

die() { echo "ERROR: $*" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE"

# Temp files hold passwords: mode 600, removed on any exit.
TMPFILES=()
trap 'rm -f "${TMPFILES[@]:-}"' EXIT
mktemp_private() {  # usage: mktemp_private VAR — sets VAR in the caller (no subshell, so cleanup sees it)
  local f
  f="$(mktemp)"
  chmod 600 "$f"
  TMPFILES+=("$f")
  printf -v "$1" '%s' "$f"
}

load_env() {
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  if [[ -f "$OWNER_ENV" ]]; then
    # shellcheck disable=SC1090
    source "$OWNER_ENV"
  fi
}

# The gitignored Secret file a Trade env is materialized from: the Owner's copy
# when it exists, otherwise the infra checkout (before the W-33 move).
trade_secret_file() {
  local env="$1"
  if [[ -f "$OWNER_DIR/secrets/bifrost-$env-secrets.yaml" ]]; then
    printf '%s' "$OWNER_DIR/secrets/bifrost-$env-secrets.yaml"
  else
    printf '%s' "$TRADE_INFRA/k8s/base/secrets/bifrost-$env-secrets.yaml"
  fi
}

# redis-cli in the redis-ib pod, authenticated as user $1 with the password in variable $2.
# The password goes in on stdin, so it is in no argv and no log.
redis_as() {
  local user="$1" var="$2"
  shift 2
  load_env
  kubectl -n data exec -i deploy/redis-ib -- \
    sh -c 'REDISCLI_AUTH="$(cat)" exec redis-cli --no-auth-warning --user "$0" "$@"' "$user" "$@" \
    <<<"${!var}"
}
redis_admin() { redis_as ib-gateway REDIS_IB_GATEWAY_PASS "$@"; }

ensure_env_passwords() {
  python3 - "$ENV_FILE" "$1" <<'PY'
import re
import secrets
import sys
from pathlib import Path

path, rotate_dev = Path(sys.argv[1]), sys.argv[2] == "1"
text = path.read_text(encoding="utf-8")


def current(name: str) -> str:
    m = re.search(rf"^{name}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip().strip('"') if m else ""


def put(name: str) -> None:
    global text
    line = f"{name}={secrets.token_hex(32)}"
    if re.search(rf"^{name}=", text, re.MULTILINE):
        text = re.sub(rf"^{name}=.*$", line, text, count=1, flags=re.MULTILINE)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    print(f"set {name} in {path} (value not shown)")


stg = current("REDIS_IB_TRADE_STG_PASS")
if not stg or stg.startswith("change-me"):
    put("REDIS_IB_TRADE_STG_PASS")
if rotate_dev:
    put("REDIS_IB_TRADE_DEV_PASS")
path.write_text(text, encoding="utf-8")
PY
}

connections_by_user() {
  redis_admin CLIENT LIST | sed -n 's/.* user=\([^ ]*\) .*/\1/p' | sort | uniq -c
}

cmd_acl() {
  local rotate=0
  [[ "${1:-}" == "--rotate-dev" ]] && rotate=1
  if (( rotate )) && connections_by_user | grep -qw trade-dev; then
    echo "note: some connections use trade-dev now; they stay up, but a reconnect with the old password will fail"
  fi
  ensure_env_passwords "$rotate"

  local acl_file want got=""
  mktemp_private acl_file
  "$ROOT/scripts/render-redis-ib-acl.sh" >"$acl_file"
  want="$(shasum -a 256 "$acl_file" | cut -d' ' -f1)"

  kubectl create secret generic redis-ib-acl -n data --from-file=acl.conf="$acl_file" \
    --dry-run=client -o yaml | kubectl apply -f -

  echo "waiting for the redis-ib pod to see the new file (the kubelet syncs Secrets within a minute or two)"
  for _ in $(seq 1 60); do
    got="$(kubectl -n data exec deploy/redis-ib -- sha256sum /etc/redis/acl.conf | cut -d' ' -f1)"
    [[ "$got" == "$want" ]] && break
    sleep 5
  done
  [[ "$got" == "$want" ]] || die "the pod still has the old file after 5 minutes; nothing was loaded"

  local out
  out="$(redis_admin ACL LOAD)"
  [[ "$out" == "OK" ]] || die "ACL LOAD refused the file, the old users stay in force: $out"
  echo "ACL LOAD: OK — users: $(redis_admin ACL USERS | tr '\n' ' ')"
  echo "trade-dev PING: $(redis_as trade-dev REDIS_IB_TRADE_DEV_PASS PING)"
  echo "trade-stg PING: $(redis_as trade-stg REDIS_IB_TRADE_STG_PASS PING)"
}

# Point bifrost-<env>-secrets (live, and the gitignored file it is materialized from) at a user.
set_trade_secret() {
  local env="$1" user="$2" var="$3" patch
  load_env
  [[ -n "${!var:-}" && "${!var}" != change-me-* ]] || die "$var is not set in $ENV_FILE or the Owner env file"
  mktemp_private patch
  REDIS_IB_SECRET_VALUE="${!var}" python3 - "$user" "$(trade_secret_file "$env")" \
    >"$patch" <<'PY'
import json
import os
import re
import sys
from pathlib import Path

user, path = sys.argv[1], Path(sys.argv[2])
pw = os.environ["REDIS_IB_SECRET_VALUE"]
if path.is_file():
    text = path.read_text(encoding="utf-8")
    for key, val in (("REDIS_IB_USERNAME", user), ("REDIS_IB_PASSWORD", pw)):
        pat = rf"(^[ \t]*{key}:[ \t]*).*$"
        if re.search(pat, text, flags=re.MULTILINE):
            text = re.sub(pat, lambda m: f'{m.group(1)}"{val}"', text, count=1, flags=re.MULTILINE)
        else:
            text = re.sub(r"(^stringData:\n)", lambda m: f'{m.group(1)}  {key}: "{val}"\n', text, count=1,
                          flags=re.MULTILINE)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"updated {path} → {user} (password not shown)", file=sys.stderr)
print(json.dumps({"stringData": {"REDIS_IB_USERNAME": user, "REDIS_IB_PASSWORD": pw}}))
PY
  kubectl -n "bifrost-$env" patch secret "bifrost-$env-secrets" --type merge --patch-file "$patch" >/dev/null
  echo "bifrost-$env/bifrost-$env-secrets → $user"
}

restart_trade() {
  local ns="$1" d
  for d in "${TRADE_DEPLOYS[@]}"; do
    kubectl -n "$ns" get deploy "$d" >/dev/null 2>&1 || continue
    kubectl -n "$ns" rollout restart deploy "$d"
  done
  for d in "${TRADE_DEPLOYS[@]}"; do
    kubectl -n "$ns" get deploy "$d" >/dev/null 2>&1 || continue
    kubectl -n "$ns" rollout status deploy "$d" --timeout=240s
  done
}

env_arg() {
  [[ "${1:-}" == dev || "${1:-}" == stg ]] || die "usage: $0 $2 dev|stg (PROD stays on trade-prod)"
}

cmd_switch() {
  env_arg "${1:-}" switch
  local env="$1" ns="bifrost-$1" user="trade-$1" var stream
  var="REDIS_IB_TRADE_$(tr '[:lower:]' '[:upper:]' <<<"$env")_PASS"
  stream="ib:operator:cmd:$env"
  kubectl -n "$ns" get cm bifrost-config -o jsonpath='{.data.config\.stg\.yaml}' | grep -q "\"$stream\"" \
    || die "$ns config still sends RPCs to the production stream; deploy the infra config change first"
  redis_admin ACL USERS | grep -qx "$user" || die "redis-ib has no $user yet; run: $0 acl"
  set_trade_secret "$env" "$user" "$var"
  restart_trade "$ns"
  echo "done. In a few minutes: $0 check"
}

cmd_rollback() {
  env_arg "${1:-}" rollback
  set_trade_secret "$1" trade-prod REDIS_IB_TRADE_PROD_PASS
  restart_trade "bifrost-$1"
}

cmd_check() {
  local minutes="${1:-60}"
  echo "== connections by user =="
  connections_by_user
  echo "== refused for trade-dev / trade-stg, last $minutes min =="
  redis_admin --json ACL LOG 128 | python3 -c '
import json, sys
minutes = float(sys.argv[1])
rows = {}
for e in json.load(sys.stdin) or []:
    if e.get("username") not in ("trade-dev", "trade-stg"):
        continue
    if float(e.get("age-seconds", 0)) > minutes * 60:
        continue
    k = (e["username"], e.get("reason"), e.get("context"), e.get("object"))
    rows[k] = rows.get(k, 0) + int(e.get("count", 1))
for (user, reason, context, obj), n in sorted(rows.items()):
    print(f"{n:>6}  {user:<10} {reason:<8} {context:<8} {obj}")
print("none" if not rows else f"{len(rows)} kind(s)")
' "$minutes"
}

case "${1:-}" in
  acl) shift; cmd_acl "$@" ;;
  switch) shift; cmd_switch "$@" ;;
  rollback) shift; cmd_rollback "$@" ;;
  check) shift; cmd_check "$@" ;;
  *) sed -n '2,19p' "$0"; exit 2 ;;
esac
