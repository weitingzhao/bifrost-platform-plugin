"""Redis key names — must match bifrost-trade-socket ib/* modules."""

IB_INGESTER_HEALTH_KEY = "bifrost:health:ws_ib_ingestor"
IB_INGESTER_CHANNEL = "ib:ingester:channel"
IB_INGESTER_TICK_PREFIX = "ib:ingester:tick:"
IB_INGESTER_TICK_TTL_SEC = 300
IB_INGESTER_SUBSCRIPTIONS_KEY = "ib:ingester:meta:subscriptions"

IB_ACCOUNT_AGENT_HEALTH_KEY = "bifrost:health:ws_ib_account_agent"
IB_ACCOUNT_SNAPSHOT_KEY = "ib:account:snapshot:v1"
IB_ACCOUNT_NOTIFY_CHANNEL = "ib:account:notify"
IB_ACCOUNT_STREAM_KEY = "ib:account:stream:v1"
IB_ACCOUNT_STREAM_MAXLEN = 1000

IB_OPERATOR_HEALTH_KEY = "bifrost:health:ws_ib_operator"
IB_OPERATOR_CMD_STREAM = "ib:operator:cmd"
IB_OPERATOR_CONSUMER_GROUP = "ib-gateway"
IB_OPERATOR_RESULT_PREFIX = "ib:operator:result:"
IB_OPERATOR_RESULT_TTL_SEC = 300

IB_GATEWAY_HEALTH_PREFIX = "ib:health:"

# Canonical STK contract_key — must match bifrost_core / trade-socket ingestor.
STK_CONTRACT_KEY_SUFFIX = "|STK|||"


def stk_contract_key(symbol: str) -> str:
    """Build legacy-compatible STK tick key suffix (e.g. ``NVDA|STK|||``)."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol required for stk_contract_key")
    return f"{sym}{STK_CONTRACT_KEY_SUFFIX}"


def ingester_tick_key(contract_key: str) -> str:
    return IB_INGESTER_TICK_PREFIX + contract_key
