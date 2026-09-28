"""One-shot quotes cancel the stream they opened.

ib_insync keys streams by id() of the contract object given to reqMktData;
cancelMktData(ticker) found nothing, logged "No reqId found" and left the
line open on TWS (every call since 2026-07-04).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from bifrost_plugin.ib_gateway.ib_ops import fetch_option_quote_one_shot, fetch_underlying_price


class _FakeIB:
    """Mirrors ib_insync's bookkeeping: streams keyed by id(contract)."""

    def __init__(self) -> None:
        self.open: Dict[int, Any] = {}
        self.not_found: List[Any] = []

    async def qualifyContractsAsync(self, *contracts: Any) -> List[Any]:
        return list(contracts)

    def reqMktData(self, contract: Any, *_args: Any) -> Any:
        ticker = SimpleNamespace(contract=contract, bid=1.0, ask=1.2, last=1.1)
        self.open[id(contract)] = ticker
        return ticker

    def cancelMktData(self, contract: Any) -> None:
        if self.open.pop(id(contract), None) is None:
            self.not_found.append(contract)


async def test_underlying_price_cancels_its_stream() -> None:
    ib = _FakeIB()
    assert await fetch_underlying_price(ib, "abc") == 1.1
    assert ib.open == {} and ib.not_found == []


async def test_option_one_shot_cancels_its_stream() -> None:
    ib = _FakeIB()
    quote = await fetch_option_quote_one_shot(ib, "abc", "20261218", 100.0, "C")
    assert quote is not None and quote["mid"] == 1.1
    assert ib.open == {} and ib.not_found == []
