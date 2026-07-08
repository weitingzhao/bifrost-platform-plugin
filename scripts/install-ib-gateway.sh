#!/usr/bin/env bash
# Build IB Gateway image and deploy to K3s data NS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
export KUBECONFIG
IMAGE="${IB_GATEWAY_IMAGE:-bifrost-platform-plugin-ib-gateway:0.1.0}"
K3S_NODE="${K3S_NODE:-vision@192.168.10.73}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

echo "== Build image $IMAGE (linux/amd64 for K3s nodes) =="
docker buildx build --platform linux/amd64 -t "$IMAGE" --load "$ROOT"

echo "== Import image to K3s nodes =="
NODES="${K3S_NODES:-vision@192.168.10.73 vision@192.168.10.70 vision@192.168.10.75 vision@192.168.10.77 vision@192.168.10.79}"
IMPORTED=0
for NODE in $NODES; do
  if docker save "$IMAGE" | ssh -o ConnectTimeout=5 "$NODE" 'sudo k3s ctr images import -' 2>/dev/null; then
    echo "Image imported via ssh $NODE"
    IMPORTED=$((IMPORTED + 1))
  else
    echo "Skip $NODE (unreachable or no k3s)"
  fi
done
if [[ "$IMPORTED" -eq 0 ]]; then
  echo "Warning: no remote import succeeded — ensure image exists on scheduled node" >&2
fi

kubectl create secret generic ib-gateway-redis \
  --namespace=data \
  --from-literal=password="${REDIS_IB_GATEWAY_PASS}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -k "$ROOT/k8s/ib-gateway"

echo "Waiting for ib-gateway rollout..."
kubectl rollout status deployment/ib-gateway -n data --timeout=120s
kubectl get pods,deploy -n data -l app.kubernetes.io/name=ib-gateway

echo "== Switch mock → live (base k8s/ib-gateway ships mock ConfigMap) =="
make -C "$ROOT" ib-gateway-set-live
