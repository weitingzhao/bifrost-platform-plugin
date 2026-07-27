# bifrost-platform-plugin

Bifrost Ops Platform **plugins** — domain-specific extensions that run alongside the core control plane (`bifrost-platform`).

## Plugins

| Plugin | Status | Description |
|--------|--------|-------------|
| **IB Gateway** | Complete (IBGP0–4) | Shared TWS connectivity bus → `redis-ib` for all Trade environments · live TWS @ .30/.32 |

### On-demand STK (Market Live)

Trade **Market API** `GET /quotes?symbols=…` registers STK symbols on redis-ib:

- `SADD ib:ingester:control:on_demand_stk`
- `HSET ib:ingester:control:on_demand_stk_ts` (heartbeat)

**IB Gateway** Host slot merges `watchlist_symbols ∪ fresh(on_demand)` into `reqMktData` (cap `max_stream_stk`, default 40). Stale heartbeats (>120s) are pruned. D10-safe — market data only, no order placement.

### On-demand OPT cache (Market Live)

Trade **Market API** `GET /quotes?contract_keys=…` registers OPT contract keys on redis-ib:

- `SADD ib:option:control:on_demand_opt`
- `HSET ib:option:control:on_demand_opt_ts` (heartbeat)
- Gateway writes `ib:option:cache:{contract_key}` (JSON, TTL 300s)

**IB Gateway** Host `_opt_cache_loop` one-shot `fetch_option_quote` for fresh keys (cap `opt_cache_max_contracts`, default 40; refresh ~30s). Not a continuous OPT stream. Optional RPC `refresh_option_cache`. D10-safe — market data only.

## Phase 0 — redis-ib infrastructure

Delivers shared IB data Redis in `data` NS:

- `redis-ib` Deployment (no persistence — all keys rebuild from TWS)
- ACL users: `ib-gateway`, `trade-prod`, `trade-dev`, `platform`
- Key patterns include `bifrost:health:daemon_*` (Trade account-sync / daemon health HSET)
- `trade-dev` is **read-only observe**; K8s Dev Trade workloads that consume streams (account-sync) must use `trade-prod`
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
