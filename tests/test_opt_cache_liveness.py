"""Opt cache loop: a hung one-shot times out, and a stalled loop is reported.

On 2026-09-28 the loop in a 20-day-old pod had stopped doing one-shots with no
log line at all, while Trade kept registering option contracts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import MagicMock, patch

from bifrost_plugin.ib_gateway import live as live_mod
from bifrost_plugin.ib_gateway.connection import ConnectionState
from bifrost_plugin.ib_gateway.live import LiveGateway
from bifrost_plugin.ib_gateway.settings import GatewaySettings, TwsSlotConfig


class _FakeIB:
    """qualify never answers for symbol HANG; everything else quotes at once."""

    def __init__(self) -> None:
        self.cancelled: List[Any] = []

    async def qualifyContractsAsync(self, *contracts: Any) -> List[Any]:
        if contracts[0].symbol == "HANG":
            await asyncio.Event().wait()
        return list(contracts)

    def reqMktData(self, contract: Any, *_args: Any) -> Any:
        return SimpleNamespace(contract=contract, bid=1.0, ask=1.2, last=1.1)

    def cancelMktData(self, contract: Any) -> None:
        self.cancelled.append(contract)


def _gateway(**overrides: Any) -> LiveGateway:
    settings = GatewaySettings(
        mode="live",
        opt_cache_pacing_sec=0.0,
        opt_cache_one_shot_timeout_sec=1.0,
        opt_cache_stale_warn_sec=120.0,
        slots=[
            TwsSlotConfig(
                slot="host",
                account_id="U1",
                ip="127.0.0.1",
                port=7496,
                client_ids=(70, 71),
                has_market_data=True,
            ),
        ],
        **overrides,
    )
    writer = MagicMock()
    gw = LiveGateway(settings, writer)
    host = gw._slots["host"]
    host.state = ConnectionState.CONNECTED
    host.ib = _FakeIB()
    return gw


async def test_hung_one_shot_times_out_and_the_loop_moves_on(caplog) -> None:
    gw = _gateway()
    keys = ["HANG|OPT|20261218|100|C", "ABC|OPT|20261218|100|C"]
    gw._opt_cache_progress_at = 0.0
    caplog.set_level(logging.WARNING, logger=live_mod.__name__)
    with patch.object(live_mod, "list_fresh_on_demand_opt", return_value=keys):
        started = time.monotonic()
        refreshed = await gw._refresh_opt_cache_once(gw._slots["host"])
        elapsed = time.monotonic() - started
    assert refreshed == 1
    assert 0.9 <= elapsed < 3.0
    gw._writer.write_opt_cache.assert_called_once()
    assert "timed out" in caplog.text
    assert time.time() - gw._opt_cache_progress_at < 5


def test_stale_loop_warns_once_per_window(caplog) -> None:
    gw = _gateway()
    now = 10_000.0
    gw._opt_cache_progress_at = now - 200
    caplog.set_level(logging.WARNING, logger=live_mod.__name__)
    assert gw._check_opt_cache_liveness(now) == 200
    assert gw._check_opt_cache_liveness(now + 10) == 210
    assert caplog.text.count("no progress") == 1


def test_fresh_loop_is_quiet(caplog) -> None:
    gw = _gateway()
    now = 10_000.0
    gw._opt_cache_progress_at = now - 5
    caplog.set_level(logging.WARNING, logger=live_mod.__name__)
    gw._check_opt_cache_liveness(now)
    assert "no progress" not in caplog.text


def test_health_dict_reports_progress_age() -> None:
    gw = _gateway()
    gw._opt_cache_progress_at = time.time() - 42
    age = gw.health_dict()["opt_cache_progress_age_sec"]
    assert 41 <= age <= 45
