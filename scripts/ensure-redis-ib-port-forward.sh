#!/usr/bin/env bash
# Ensure kubectl port-forward to Platform redis-ib on localhost (default :6380).
set -euo pipefail

PORT="${REDIS_IB_PORT:-6380}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG

if nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
  echo "  redis-ib port-forward already listening on 127.0.0.1:${PORT}"
  exit 0
fi

echo "  Starting kubectl port-forward redis-ib → 127.0.0.1:${PORT} ..."
kubectl port-forward -n data "svc/redis-ib" "${PORT}:6379" >/tmp/redis-ib-pf.log 2>&1 &
disown
for _ in $(seq 1 15); do
  if nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
    echo "  redis-ib port-forward ready on :${PORT}"
    exit 0
  fi
  sleep 1
done
echo "ERROR: redis-ib port-forward failed — see /tmp/redis-ib-pf.log" >&2
exit 1
