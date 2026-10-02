#!/usr/bin/env bash
# Apply redis-ib to data NS — creates ACL secret from .env then kubectl apply -k.
# A running redis-ib does not re-read the file on its own: to change users on a live bus use
# scripts/redis-ib-env-users.sh acl (ACL LOAD, connections stay up), not a pod restart — redis-ib
# keeps nothing on disk, so a restart empties the bus.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ACL_FILE="$(mktemp)"
chmod 600 "$ACL_FILE"
trap 'rm -f "$ACL_FILE"' EXIT
"$ROOT/scripts/render-redis-ib-acl.sh" > "$ACL_FILE"

kubectl create namespace data --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic redis-ib-acl \
  --namespace=data \
  --from-file=acl.conf="$ACL_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -k "$ROOT/k8s/redis-ib"

echo "redis-ib applied. Verify: kubectl get pods,svc,pdb -n data -l app.kubernetes.io/name=redis-ib"
