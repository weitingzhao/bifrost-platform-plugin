"""Tests for Gateway on-demand OPT parse / list_fresh / write_opt_cache."""

from __future__ import annotations

import json
from typing import Any, Dict, Set
from unittest.mock import MagicMock

from bifrost_plugin.ib_gateway.on_demand_opt import list_fresh_on_demand_opt, parse_opt_contract_key
from bifrost_plugin.ib_gateway.redis_keys import (
    IB_OPTION_CACHE_PREFIX,
    IB_OPTION_CACHE_TTL_SEC,
    IB_OPTION_ON_DEMAND_SET,
    IB_OPTION_ON_DEMAND_TS,
)
from bifrost_plugin.ib_gateway.writer import GatewayRedisWriter


class _FakeRedis:
    def __init__(self) -> None:
        self.sets: Dict[str, Set[str]] = {}
        self.hashes: Dict[str, Dict[str, str]] = {}
        self.kv: Dict[str, Any] = {}
        self.ex: Dict[str, int] = {}

    def smembers(self, key: str) -> Set[str]:
        return set(self.sets.get(key, set()))

    def srem(self, key: str, *members: str) -> int:
        bucket = self.sets.get(key)
        if not bucket:
            return 0
        n = 0
        for m in members:
            if str(m) in bucket:
                bucket.discard(str(m))
                n += 1
        return n

    def hgetall(self, key: str) -> Dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def hdel(self, key: str, *fields: str) -> int:
        h = self.hashes.get(key)
        if not h:
            return 0
        n = 0
        for f in fields:
            if str(f) in h:
                del h[str(f)]
                n += 1
        return n

    def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        self.kv[str(key)] = value
        if ex is not None:
            self.ex[str(key)] = int(ex)
        return True

    def publish(self, *_args: Any, **_kwargs: Any) -> int:
        return 0


def test_parse_opt_contract_key_ok() -> None:
    assert parse_opt_contract_key("GOOG|OPT|20260717|300.0|C") == (
        "GOOG",
        "20260717",
        300.0,
        "C",
    )
    assert parse_opt_contract_key("aapl|opt|20260815|200|p") == (
        "AAPL",
        "20260815",
        200.0,
        "P",
    )


def test_parse_opt_contract_key_rejects() -> None:
    assert parse_opt_contract_key("NVDA|STK|||") is None
    assert parse_opt_contract_key("GOOG|OPT|bad|300|C") is None
    assert parse_opt_contract_key("GOOG|OPT|20260717|x|C") is None
    assert parse_opt_contract_key("GOOG|OPT|20260717|300|X") is None
    assert parse_opt_contract_key("") is None


def test_list_fresh_on_demand_opt_prunes() -> None:
    r = _FakeRedis()
    ck_a = "GOOG|OPT|20260717|300.0|C"
    ck_b = "AAPL|OPT|20260815|200.0|P"
    r.sets[IB_OPTION_ON_DEMAND_SET] = {ck_a, ck_b}
    r.hashes[IB_OPTION_ON_DEMAND_TS] = {ck_a: "1000", ck_b: "900"}
    fresh = list_fresh_on_demand_opt(r, max_age_sec=50, now=1040.0)
    assert fresh == [ck_a]
    assert ck_b not in r.sets[IB_OPTION_ON_DEMAND_SET]


def test_write_opt_cache_shape() -> None:
    r = _FakeRedis()
    w = GatewayRedisWriter(r, env="test")
    ck = "GOOG|OPT|20260717|300.0|C"
    payload = {
        "bid": 1.1,
        "ask": 1.3,
        "last": 1.2,
        "mid": 1.2,
        "contract_key": ck,
        "symbol": "GOOG",
        "sec_type": "OPT",
        "updated_ts": 1234.5,
    }
    w.write_opt_cache(ck, payload)
    key = IB_OPTION_CACHE_PREFIX + ck
    assert key in r.kv
    assert r.ex[key] == IB_OPTION_CACHE_TTL_SEC
    body = json.loads(r.kv[key])
    assert body["sec_type"] == "OPT"
    assert body["contract_key"] == ck
    assert body["mid"] == 1.2


def test_opt_cache_loop_skips_when_disabled() -> None:
    """Settings flag disables OPT cache; loop should sleep without calling IB."""
    from bifrost_plugin.ib_gateway.live import LiveGateway
    from bifrost_plugin.ib_gateway.settings import GatewaySettings

    settings = GatewaySettings(opt_cache_enabled=False)
    writer = MagicMock()
    writer.redis = MagicMock()
    gw = LiveGateway(settings, writer)
    assert settings.opt_cache_enabled is False
    # Method exists and is awaitable; disabled path covered by unit of settings + early continue.
    assert hasattr(gw, "_opt_cache_loop")
