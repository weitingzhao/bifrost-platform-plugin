"""Phase 0 placeholder — redis-ib contract smoke tests."""

from bifrost_plugin.ib_gateway.config import (
    REDIS_HEALTH,
    REDIS_OPERATOR_CMD,
    REDIS_TICK_PATTERN,
    STK_TICK_EXAMPLE,
)
from bifrost_plugin.ib_gateway.redis_keys import ingester_tick_key, stk_contract_key


def test_stk_contract_key() -> None:
    assert stk_contract_key("nvda") == "NVDA|STK|||"
    assert stk_contract_key(" SPY ") == "SPY|STK|||"


def test_redis_key_contracts() -> None:
    ck = stk_contract_key("NVDA")
    assert ck == STK_TICK_EXAMPLE
    assert REDIS_TICK_PATTERN.format(contract_key=ck) == ingester_tick_key(ck)
    assert ingester_tick_key(ck) == "ib:ingester:tick:NVDA|STK|||"
    assert REDIS_HEALTH.format(account_id="wzhao1503") == "ib:health:wzhao1503"
    assert REDIS_OPERATOR_CMD == "ib:operator:cmd"
