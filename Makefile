.PHONY: install-dev install-redis-ib apply-external-names verify-redis-ib install-ib-gateway verify-ib-gateway verify-ib-gateway-live verify-ib-gateway-rpc-parity verify-trade-ib-health verify-trade-celery-bars verify-trade-ib-ui verify-trade-ib-migration-program verify-trade-ib-migration-program-dev sync-redis-ib-dev-compose-config rollout-tibm-w1-stg verify-trade-ib-w1-stg rollout-tibm-w2-stg verify-trade-ib-w2-stg rollout-tibm-w3-stg verify-trade-ib-w3-stg verify-trade-ib-rollout-stg rollout-tibm-dev-compose verify-trade-ib-rollout-dev-compose rollout-tibm-prod verify-trade-ib-w1-prod verify-trade-ib-w2-prod verify-trade-ib-w3-prod verify-trade-ib-rollout-prod rollout-tibm-strategy verify-tibm-strategy-alignment ib-gateway-set-live verify-ib-gateway-program verify-trade-cutover verify-trade-quotes-e2e sync-redis-ib-secrets test lint

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

verify-trade-ib-migration-program-dev:
	chmod +x scripts/verify-trade-ib-migration-program-dev.sh scripts/verify-trade-ib-dev-read.sh
	./scripts/verify-trade-ib-migration-program-dev.sh

verify-trade-ib-dev-read:
	chmod +x scripts/verify-trade-ib-dev-read.sh
	./scripts/verify-trade-ib-dev-read.sh

sync-redis-ib-dev-compose-config:
	chmod +x scripts/sync-redis-ib-dev-compose-config.sh
	./scripts/sync-redis-ib-dev-compose-config.sh

rollout-tibm-w1-stg:
	chmod +x scripts/rollout-tibm-w1-stg.sh
	./scripts/rollout-tibm-w1-stg.sh

verify-trade-ib-w1-stg:
	chmod +x scripts/verify-trade-ib-w1-stg.sh
	./scripts/verify-trade-ib-w1-stg.sh

rollout-tibm-w2-stg:
	chmod +x scripts/rollout-tibm-w2-stg.sh
	./scripts/rollout-tibm-w2-stg.sh

verify-trade-ib-w2-stg:
	chmod +x scripts/verify-trade-ib-w2-stg.sh
	./scripts/verify-trade-ib-w2-stg.sh

rollout-tibm-w3-stg:
	chmod +x scripts/rollout-tibm-w3-stg.sh
	./scripts/rollout-tibm-w3-stg.sh

verify-trade-ib-w3-stg:
	chmod +x scripts/verify-trade-ib-w3-stg.sh
	./scripts/verify-trade-ib-w3-stg.sh

verify-trade-ib-rollout-stg:
	chmod +x scripts/verify-trade-ib-rollout-stg.sh
	./scripts/verify-trade-ib-rollout-stg.sh

rollout-tibm-dev-compose:
	chmod +x scripts/rollout-tibm-dev-compose.sh scripts/ensure-redis-ib-port-forward.sh
	./scripts/rollout-tibm-dev-compose.sh

verify-trade-ib-rollout-dev-compose:
	chmod +x scripts/verify-trade-ib-rollout-dev-compose.sh scripts/ensure-redis-ib-port-forward.sh
	./scripts/verify-trade-ib-rollout-dev-compose.sh

rollout-tibm-prod:
	chmod +x scripts/rollout-tibm-prod.sh scripts/lib/tibm_prod_defaults.sh
	./scripts/rollout-tibm-prod.sh

verify-trade-ib-w1-prod:
	chmod +x scripts/verify-trade-ib-w1-prod.sh scripts/lib/tibm_prod_defaults.sh
	./scripts/verify-trade-ib-w1-prod.sh

verify-trade-ib-w2-prod:
	chmod +x scripts/verify-trade-ib-w2-prod.sh scripts/lib/tibm_prod_defaults.sh
	./scripts/verify-trade-ib-w2-prod.sh

verify-trade-ib-w3-prod:
	chmod +x scripts/verify-trade-ib-w3-prod.sh scripts/lib/tibm_prod_defaults.sh
	./scripts/verify-trade-ib-w3-prod.sh

verify-trade-ib-rollout-prod:
	chmod +x scripts/verify-trade-ib-rollout-prod.sh scripts/lib/tibm_prod_defaults.sh
	./scripts/verify-trade-ib-rollout-prod.sh

rollout-tibm-strategy:
	chmod +x scripts/rollout-tibm-strategy.sh
	./scripts/rollout-tibm-strategy.sh

verify-tibm-strategy-alignment:
	chmod +x scripts/verify-tibm-strategy-alignment.sh scripts/lib/tibm_prod_defaults.sh
	./scripts/verify-tibm-strategy-alignment.sh

ib-gateway-set-live:
	chmod +x scripts/ib-gateway-set-live.sh
	./scripts/ib-gateway-set-live.sh

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
