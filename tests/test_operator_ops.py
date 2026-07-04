"""Mock gateway — all ALL_OPS parity tests."""

from __future__ import annotations

import asyncio

import pytest

from bifrost_plugin.ib_gateway.mock import MockGateway
from bifrost_plugin.ib_gateway.protocol import CommandMessage
from bifrost_plugin.ib_gateway.settings import GatewaySettings, TwsSlotConfig
from bifrost_plugin.ib_gateway.writer import GatewayRedisWriter

ALL_OPS = (
    "ping",
    "disconnect_all",
    "reconnect_all",
    "fetch_accounts_snapshot",
    "fetch_bars",
    "fetch_bars_range",
    "fetch_executions",
    "fetch_option_expirations",
    "fetch_option_snapshot",
)


class _NoopWriter(GatewayRedisWriter):
    def __init__(self) -> None:
        pass  # type: ignore[call-arg]

    def write_tick(self, *args, **kwargs) -> None:
        pass

    def write_account_snapshot(self, *args, **kwargs) -> None:
        pass

    def write_ingestor_health(self, *args, **kwargs) -> None:
        pass

    def write_account_health(self, *args, **kwargs) -> None:
        pass

    def write_operator_health(self, *args, **kwargs) -> None:
        pass

    def write_plugin_health(self, *args, **kwargs) -> None:
        pass

    def set_subscriptions(self, *args, **kwargs) -> None:
        pass

    def write_operator_result(self, *args, **kwargs) -> None:
        pass


def _gateway() -> MockGateway:
    settings = GatewaySettings(
        mode="mock",
        watchlist_symbols=["NVDA", "SPY"],
        slots=[
            TwsSlotConfig(
                slot="host",
                account_id="wzhao1503",
                ip="127.0.0.1",
                port=7496,
                client_ids=(1, 2),
                has_market_data=True,
            )
        ],
    )
    return MockGateway(settings, _NoopWriter())


@pytest.mark.parametrize("op", ALL_OPS)
@pytest.mark.asyncio
async def test_mock_gateway_supports_all_ops(op: str) -> None:
    gw = _gateway()
    payload: dict = {}
    if op in ("fetch_bars", "fetch_bars_range", "fetch_option_expirations", "fetch_option_snapshot"):
        payload = {"symbol": "NVDA"}
    if op == "fetch_option_snapshot":
        payload = {"symbol": "NVDA", "expiration": "20260718", "strikes": [130.0]}
    msg = CommandMessage(
        req_id=f"test-{op}",
        version="1",
        op=op,
        payload=payload,
        caller="pytest",
        deadline_ms=None,
        stream_id="0-0",
    )
    result = await gw.handle_command(msg)
    assert result.get("ok") is True, f"{op} failed: {result}"


@pytest.mark.asyncio
async def test_fetch_bars_range_returns_bar_time() -> None:
    gw = _gateway()
    msg = CommandMessage(
        req_id="bars-range",
        version="1",
        op="fetch_bars_range",
        payload={"symbol": "SPY", "period": "1 D"},
        caller="pytest",
        deadline_ms=None,
        stream_id="0-0",
    )
    result = await gw.handle_command(msg)
    assert result["ok"] is True
    bars = result["data"]["bars"]
    assert len(bars) >= 1
    assert "bar_time" in bars[0]
