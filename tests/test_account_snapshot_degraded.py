"""A failed IB read is not an empty account book (TD-212) and open orders are read-only (TD-211)."""

from __future__ import annotations

import asyncio
from typing import Any

from bifrost_plugin.ib_gateway.ib_ops import fetch_accounts_snapshot_rows, fetch_open_orders


class _Value:
    def __init__(self, tag: str, value: str) -> None:
        self.tag = tag
        self.value = value


class _Pos:
    def __init__(self) -> None:
        self.account = "U0000001"
        self.position = 1.0
        self.avgCost = 10.0
        self.contract = type("C", (), {"symbol": "ZZZ", "secType": "STK", "exchange": "SMART", "currency": "USD"})()


class _Ib:
    def __init__(self, *, positions_error: bool = False, summary_error: bool = False) -> None:
        self.positions_error = positions_error
        self.summary_error = summary_error

    def isConnected(self) -> bool:
        return True

    def managedAccounts(self) -> list[str]:
        return ["U0000001"]

    async def reqPositionsAsync(self) -> None:
        if self.positions_error:
            raise RuntimeError("Socket disconnect")

    def positions(self) -> list[Any]:
        return [_Pos()]

    async def accountSummaryAsync(self, aid: str) -> list[_Value]:
        if self.summary_error:
            raise RuntimeError("Not connected")
        return [_Value("NetLiquidation", "1000"), _Value("Account", aid)]


def test_positions_read_failure_omits_the_positions_key() -> None:
    rows = asyncio.run(fetch_accounts_snapshot_rows(_Ib(positions_error=True)))
    assert len(rows) == 1
    assert rows[0]["positions_ok"] is False
    assert "positions" not in rows[0]


def test_summary_read_failure_omits_net_liquidation() -> None:
    rows = asyncio.run(fetch_accounts_snapshot_rows(_Ib(summary_error=True)))
    assert "NetLiquidation" not in rows[0]["summary"]
    assert rows[0]["summary_ok"] is False


def test_successful_reads_keep_positions_and_nav() -> None:
    rows = asyncio.run(fetch_accounts_snapshot_rows(_Ib()))
    assert rows[0]["positions_ok"] is True
    assert rows[0]["positions"][0]["symbol"] == "ZZZ"
    assert rows[0]["summary"]["NetLiquidation"] == "1000"


class _Order:
    orderId = 7
    permId = 70
    account = "U0000001"
    action = "BUY"
    totalQuantity = 3
    lmtPrice = 1.5


class _Status:
    filled = 0
    remaining = 3
    status = "Submitted"


class _Contract:
    symbol = "ZZZ"
    secType = "STK"
    lastTradeDateOrContractMonth = ""
    strike = 0
    right = ""


class _Trade:
    order = _Order()
    orderStatus = _Status()
    contract = _Contract()


class _OrdersIb:
    def isConnected(self) -> bool:
        return True

    async def reqOpenOrdersAsync(self) -> list[_Trade]:
        return [_Trade()]


def test_open_orders_use_req_open_orders_only() -> None:
    rows = asyncio.run(fetch_open_orders(_OrdersIb()))
    assert rows == [
        {
            "order_id": 7,
            "perm_id": 70,
            "account_id": "U0000001",
            "symbol": "ZZZ",
            "sec_type": "STK",
            "action": "BUY",
            "total_quantity": 3.0,
            "filled": 0.0,
            "remaining": 3.0,
            "limit_price": 1.5,
            "status": "Submitted",
            "contract_key": "ZZZ|STK|||",
        }
    ]


def test_fetch_open_orders_does_not_define_a_write() -> None:
    import bifrost_plugin.ib_gateway.ib_ops as ops

    src = ops.__file__
    text = open(src, encoding="utf-8").read()
    for banned in ("placeOrder", "cancelOrder", "reqModifyOrder"):
        assert banned not in text
