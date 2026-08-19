"""Tests for Gateway on-demand STK merge / budget."""

from __future__ import annotations

from typing import Dict, Set

from bifrost_plugin.ib_gateway.on_demand import build_desired_stk_symbols, list_fresh_on_demand_stk
from bifrost_plugin.ib_gateway.redis_keys import (
    IB_INGESTER_ON_DEMAND_STK,
    IB_INGESTER_ON_DEMAND_STK_TS,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.sets: Dict[str, Set[str]] = {}
        self.hashes: Dict[str, Dict[str, str]] = {}

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


def test_build_desired_prefers_watchlist_under_cap() -> None:
    desired, truncated = build_desired_stk_symbols(
        ["NVDA", "AAPL"],
        ["SGOV", "GOOG", "DAVE"],
        max_stream_stk=4,
    )
    assert desired == ["NVDA", "AAPL", "SGOV", "GOOG"]
    assert truncated is True


def test_build_desired_no_truncate() -> None:
    desired, truncated = build_desired_stk_symbols(
        ["NVDA"],
        ["SGOV"],
        max_stream_stk=40,
    )
    assert desired == ["NVDA", "SGOV"]
    assert truncated is False


def test_list_fresh_prunes_stale() -> None:
    r = _FakeRedis()
    r.sets[IB_INGESTER_ON_DEMAND_STK] = {"SGOV", "GOOG"}
    r.hashes[IB_INGESTER_ON_DEMAND_STK_TS] = {"SGOV": "1000", "GOOG": "900"}
    fresh = list_fresh_on_demand_stk(r, max_age_sec=50, now=1040.0)
    assert fresh == ["SGOV"]
    assert "GOOG" not in r.sets[IB_INGESTER_ON_DEMAND_STK]
