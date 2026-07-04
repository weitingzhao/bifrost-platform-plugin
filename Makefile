.PHONY: install-dev install-redis-ib apply-external-names verify-redis-ib install-ib-gateway verify-ib-gateway verify-ib-gateway-live verify-ib-gateway-rpc-parity verify-trade-ib-health verify-trade-celery-bars verify-trade-ib-ui verify-trade-ib-migration-program verify-ib-gateway-program verify-trade-cutover verify-trade-quotes-e2e sync-redis-ib-secrets test lint

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

verify-trade-ib-health:
	chmod +x scripts/verify-trade-ib-health.sh
	./scripts/verify-trade-ib-health.sh

verify-trade-celery-bars:
	chmod +x scripts/verify-trade-celery-bars.sh
	./scripts/verify-trade-celery-bars.sh

verify-trade-ib-ui:
	chmod +x scripts/verify-trade-ib-ui.sh
	./scripts/verify-trade-ib-ui.sh

verify-trade-ib-migration-program:
	chmod +x scripts/verify-trade-ib-migration-program.sh
	./scripts/verify-trade-ib-migration-program.sh

verify-ib-gateway-program:
	chmod +x scripts/verify-ib-gateway-program.sh
	./scripts/verify-ib-gateway-program.sh

verify-trade-cutover:
	chmod +x scripts/verify-trade-cutover.sh scripts/lib/redis_operator_ping.sh
	./scripts/verify-trade-cutover.sh

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
