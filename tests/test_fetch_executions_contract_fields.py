"""fetch_executions sends what an option fill needs to be stored (plugin 0.4.1).

Core's execution writer builds an option's contract key from expiry / strike / option_right
(``SYMBOL  YYMMDDR########|OPT|YYYYMMDD|STRIKE|R``). The plugin sent only symbol and secType,
so since core 0.60.1 an intraday option fill is refused (it would be a keyless row) and shows
up only with Flex the next day. Now the row carries the contract fields under core's names.

Built from ib_insync's own Fill / Execution / Contract classes; accounts, ids and numbers are
invented.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, List

from ib_insync import CommissionReport, Execution, Fill, Option, Stock

from bifrost_plugin.ib_gateway.ib_ops import fetch_executions

T0 = datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc)


class _Event:
    """``+=`` / ``-=`` like ib_insync's eventkit events; never fires here."""

    def __iadd__(self, _handler: Any) -> "_Event":
        return self

    def __isub__(self, _handler: Any) -> "_Event":
        return self


class _IB:
    def __init__(self, fills: List[Any]) -> None:
        self._fills = fills
        self.commissionReportEvent = _Event()

    async def reqExecutionsAsync(self, _filter: Any) -> List[Any]:
        return self._fills


def _fill(contract: Any, exec_id: str, side: str = "BOT", shares: float = 1.0) -> Fill:
    ex = Execution(
        execId=exec_id, time=T0, acctNumber="U0000001", exchange="CBOE", side=side,
        shares=shares, price=1.25, cumQty=shares, permId=1, orderId=0,
    )
    return Fill(contract=contract, execution=ex, commissionReport=CommissionReport(execId=exec_id, commission=0.5), time=T0)


def _rows(*fills: Fill) -> List[dict]:
    return asyncio.run(fetch_executions(_IB(list(fills)), wait_commission=False))


def test_an_option_fill_carries_expiry_strike_right_and_multiplier() -> None:
    opt = Option("ZZQ", "20260117", 12.5, "C", "SMART", multiplier="100", currency="USD")
    opt.conId = 4242
    (row,) = _rows(_fill(opt, "0000a.0001.01.01"))
    assert row["sec_type"] == "OPT"
    assert row["expiry"] == "20260117"
    assert row["strike"] == 12.5
    assert row["option_right"] == "C"
    assert row["multiplier"] == 100.0
    assert row["conid"] == 4242
    assert row["currency"] == "USD"
    assert row["exchange"] == "CBOE"
    assert row["cum_qty"] == 1.0
    # the fill itself is unchanged
    assert (row["exec_id"], row["account"], row["shares"], row["ts"]) == ("0000a.0001.01.01", "U0000001", 1.0, T0.timestamp())


def test_a_put_written_as_PUT_is_P() -> None:
    (row,) = _rows(_fill(Option("ZZQ", "20260117", 10, "PUT", "SMART"), "0000b.0002.01.01"))
    assert row["option_right"] == "P"


def test_a_stock_fill_has_no_option_fields() -> None:
    stk = Stock("ZZQ", "SMART", "USD")
    stk.conId = 77
    (row,) = _rows(_fill(stk, "0000c.0003.01.01", side="SLD", shares=10.0))
    assert row["sec_type"] == "STK"
    assert not {"expiry", "strike", "option_right", "multiplier"} & row.keys()
    assert row["conid"] == 77 and row["currency"] == "USD"


def test_a_field_the_contract_lacks_is_left_out_not_sent_empty() -> None:
    (row,) = _rows(_fill(Option("ZZQ"), "0000d.0004.01.01"))
    assert not {"expiry", "strike", "option_right", "multiplier", "conid", "currency"} & row.keys()


def test_the_rows_core_maps_are_complete_option_rows() -> None:
    """The names match core's passthrough list (bifrost_core.portfolio.gateway_fills._PASSTHROUGH)."""
    (row,) = _rows(_fill(Option("ZZQ", "20260117", 12.5, "C", "SMART", multiplier="100"), "0000e.0005.01.01"))
    core_names = {"exec_id", "account_id", "time", "symbol", "sec_type", "side", "quantity", "price",
                  "commission", "realized_pnl", "currency", "expiry", "strike", "option_right", "exchange",
                  "order_id", "cum_qty", "contract_key", "conid", "multiplier"}
    plugin_only = {"account", "shares", "ts"}  # renamed by core to account_id / quantity / time
    assert set(row) <= core_names | plugin_only
    assert {"expiry", "strike", "option_right"} <= set(row)
