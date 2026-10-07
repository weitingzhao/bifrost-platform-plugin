.PHONY: install-dev install-redis-ib apply-external-names verify-redis-ib install-ib-gateway verify-ib-gateway verify-ib-gateway-live verify-ib-gateway-rpc-parity sync-redis-ib-dev-compose-config ib-gateway-set-live verify-ib-gateway-program verify-trade-quotes-e2e sync-redis-ib-secrets test lint

KUBECONFIG ?= $(HOME)/.kube/bifrost-k3s.yaml
export KUBECONFIG

install-dev:
	pip install -e ".[dev,ib]"

install-redis-ib:
	./scripts/install-redis-ib.sh

apply-external-names:
	./scripts/apply-external-names.sh

verify-redis-ib:
	./scripts/verify-redis-ib.sh

install-ib-gateway:
	chmod +x scripts/install-ib-gateway.sh scripts/verify-ib-gateway.sh
	./scripts/install-ib-gateway.sh

verify-ib-gateway:
	./scripts/verify-ib-gateway.sh

verify-ib-gateway-live:
	chmod +x scripts/verify-ib-gateway-live.sh
	./scripts/verify-ib-gateway-live.sh

verify-ib-gateway-rpc-parity:
	chmod +x scripts/verify-ib-gateway-rpc-parity.sh
	./scripts/verify-ib-gateway-rpc-parity.sh

# TIBM-era verify scripts live in scripts/archive and are not current procedures (TD-125).

sync-redis-ib-dev-compose-config:
	chmod +x scripts/sync-redis-ib-dev-compose-config.sh
	./scripts/sync-redis-ib-dev-compose-config.sh

ib-gateway-set-live:
	chmod +x scripts/ib-gateway-set-live.sh
	./scripts/ib-gateway-set-live.sh

verify-ib-gateway-program:
	chmod +x scripts/verify-ib-gateway-program.sh
	./scripts/verify-ib-gateway-program.sh

verify-trade-quotes-e2e:
	chmod +x scripts/verify-trade-quotes-e2e.sh
	./scripts/verify-trade-quotes-e2e.sh

sync-redis-ib-secrets:
	chmod +x scripts/sync_redis_ib_secrets.sh
	./scripts/sync_redis_ib_secrets.sh

test:
	pytest -q

lint:
	ruff check src tests
