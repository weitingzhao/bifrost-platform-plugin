#!/usr/bin/env bash
# Poll ib:operator:result after XADD — shared by verify-*.sh scripts.
# Usage: redis_operator_ping REDIS_URL REQ_ID [MAX_WAIT_SEC]
redis_operator_ping() {
  local redis_url="$1"
  local req_id="$2"
  local max_wait="${3:-15}"
  local i result
  kubectl exec -n data deploy/redis-ib -- redis-cli -u "$redis_url" \
    XADD ib:operator:cmd '*' req_id "$req_id" v 1 op ping payload '{}' caller verify-lib >/dev/null
  for ((i = 1; i <= max_wait; i++)); do
    sleep 1
    result=$(kubectl exec -n data deploy/redis-ib -- redis-cli -u "$redis_url" GET "ib:operator:result:${req_id}" 2>/dev/null || true)
    if echo "$result" | grep -q '"ok"'; then
      echo "$result"
      return 0
    fi
  done
  echo "FAIL operator ping timeout req_id=$req_id last=[$result]" >&2
  return 1
}
