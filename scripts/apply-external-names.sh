#!/usr/bin/env bash
# ExternalName aliases — Trade NS short name redis-ib → data NS FQDN.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="redis-ib.data.svc.cluster.local"

for NS in bifrost-dev bifrost-stg bifrost-prod; do
  kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: redis-ib
  namespace: ${NS}
  labels:
    app.kubernetes.io/name: redis-ib
    bifrost.io/redis-role: ib-data
    bifrost.io/external-alias: "true"
spec:
  type: ExternalName
  externalName: ${TARGET}
  ports:
    - name: redis
      port: 6379
      targetPort: 6379
EOF
  echo "Applied redis-ib ExternalName in ${NS} → ${TARGET}"
done
