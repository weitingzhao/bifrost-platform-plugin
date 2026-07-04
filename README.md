# bifrost-platform-plugin

Bifrost Ops Platform **plugins** — domain-specific extensions that run alongside the core control plane (`bifrost-platform`).

## Plugins

| Plugin | Status | Description |
|--------|--------|-------------|
| **IB Gateway** | Complete (IBGP0–4) | Shared TWS connectivity bus → `redis-ib` for all Trade environments · live TWS @ .30/.32 |

## Phase 0 — redis-ib infrastructure

Delivers shared IB data Redis in `data` NS:

- `redis-ib` Deployment (no persistence — all keys rebuild from TWS)
- ACL users: `ib-gateway`, `trade-prod`, `trade-dev`, `platform`
- NetworkPolicy: ingress from Trade + Platform NS only
- ExternalName aliases in `bifrost-{dev,stg,prod}`

### Install

```bash
cp .env.example .env
# Edit passwords in .env

make install-redis-ib
make apply-external-names
```

### Verify

```bash
kubectl get pods,svc,pdb -n data -l app.kubernetes.io/name=redis-ib
kubectl exec -n data deploy/redis-ib -- redis-cli -u "redis://trade-dev:${REDIS_IB_TRADE_DEV_PASS}@localhost:6379" PING
```

Sign-off: **Ops Console → Architecture → Plugins → IB Gateway → Phase 0 sign-off panel**

## Repo layout

```
src/bifrost_plugin/ib_gateway/   # IB Gateway Python package (Phase 1+)
k8s/redis-ib/                    # Shared IB Redis
k8s/ib-gateway/                  # Gateway StatefulSet (Phase 1+)
k8s/external-names/              # Cross-NS aliases
scripts/                         # Install helpers
```
