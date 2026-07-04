#!/usr/bin/env bash
# Resolve Platform redis-ib ACL for TIBM verify scripts (trade-prod default, trade-dev for dev-compose).
tibm_redis_acl_user() {
  echo "${TIBM_REDIS_ACL_USER:-trade-prod}"
}

tibm_redis_acl_pass() {
  local user
  user="$(tibm_redis_acl_user)"
  case "$user" in
    trade-dev) echo "${REDIS_IB_TRADE_DEV_PASS:?REDIS_IB_TRADE_DEV_PASS missing}" ;;
    trade-prod) echo "${REDIS_IB_TRADE_PROD_PASS:?REDIS_IB_TRADE_PROD_PASS missing}" ;;
    *) echo "ERROR: unknown TIBM_REDIS_ACL_USER=$user" >&2; return 1 ;;
  esac
}

tibm_redis_url() {
  local user pass
  user="$(tibm_redis_acl_user)"
  pass="$(tibm_redis_acl_pass)"
  echo "redis://${user}:${pass}@127.0.0.1:6379"
}
