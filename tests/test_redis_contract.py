"""Phase 0 placeholder — redis-ib contract smoke tests."""

from bifrost_plugin.ib_gateway.config import (
    REDIS_HEALTH,
    REDIS_OPERATOR_CMD,
    REDIS_TICK_PATTERN,
)


def test_redis_key_contracts() -> None:
    assert REDIS_TICK_PATTERN.format(symbol="NVDA") == "ib:ingester:tick:NVDA"
    assert REDIS_HEALTH.format(account_id="wzhao1503") == "ib:health:wzhao1503"
    assert REDIS_OPERATOR_CMD == "ib:operator:cmd"
