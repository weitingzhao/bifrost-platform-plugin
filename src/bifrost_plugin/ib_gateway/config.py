"""IB Gateway configuration — account registry and redis-ib endpoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountConfig:
    account_id: str
    tws_host: str
    tws_port: int
    has_market_data: bool
    cid_pool: tuple[int, ...] = (1, 2)


@dataclass(frozen=True)
class RedisIbConfig:
    host: str = "redis-ib.data.svc.cluster.local"
    port: int = 6379
    username: str = "ib-gateway"


REDIS_IB_KEY_PREFIX = "ib:"

# Shared key namespaces (must stay aligned with Trade consumers)
REDIS_TICK_PATTERN = "ib:ingester:tick:{contract_key}"
STK_TICK_EXAMPLE = "NVDA|STK|||"
REDIS_ACCOUNT_POSITIONS = "ib:account:{account_id}:positions"
REDIS_ACCOUNT_SUMMARY = "ib:account:{account_id}:summary"
REDIS_OPERATOR_CMD = "ib:operator:cmd"
REDIS_OPERATOR_RESULT = "ib:operator:result:{request_id}"
REDIS_HEALTH = "ib:health:{account_id}"
REDIS_EVENTS = "ib:events:{account_id}"
REDIS_CONTROL = "ib:control:{account_id}"
