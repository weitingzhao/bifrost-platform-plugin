# Shared prod rollout defaults for TIBM verify/rollout scripts.
PROD_REGISTRY="${PROD_REGISTRY:-192.168.10.73:30500}"
PROD_TAG="${PROD_TAG:-prod}"
PROD_NAMESPACE="${PROD_NAMESPACE:-bifrost-prod}"
# Prod gateway Host — trade.bifrost.lan works after IngressRoute OR fix (2026-07-04).
PROD_GATEWAY_HOST="${PROD_GATEWAY_HOST:-trade.bifrost.lan}"
PROD_GATEWAY_IP="${PROD_GATEWAY_IP:-192.168.10.70}"
