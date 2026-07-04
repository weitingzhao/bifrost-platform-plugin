"""Mock IB Gateway — no TWS socket; writes legacy-compatible redis-ib keys."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Dict, List

from bifrost_plugin.ib_gateway.protocol import CommandMessage, dumps_result
from bifrost_plugin.ib_gateway.settings import GatewaySettings
from bifrost_plugin.ib_gateway.writer import GatewayRedisWriter

logger = logging.getLogger(__name__)

_MOCK_CLIENT_ID = 0


class MockGateway:
    def __init__(self, settings: GatewaySettings, writer: GatewayRedisWriter) -> None:
        self._settings = settings
        self._writer = writer
        self._prices: Dict[str, float] = {
            "NVDA": 130.0,
            "AAPL": 220.0,
            "SPY": 560.0,
            "QQQ": 480.0,
            "TSLA": 250.0,
        }
        self._cmd_count = 0

    async def run(self, stop: asyncio.Event) -> None:
        tasks = [
            asyncio.create_task(self._tick_loop(stop)),
            asyncio.create_task(self._health_loop(stop)),
        ]
        await asyncio.gather(*tasks)

    async def handle_command(self, msg: CommandMessage) -> Dict[str, Any]:
        self._cmd_count += 1
        if msg.op == "ping":
            return {
                "ok": True,
                "data": {
                    "mode": "mock",
                    "cmd_count": self._cmd_count,
                    "slots": [s.slot for s in self._settings.slots],
                },
            }
        if msg.op == "fetch_accounts_snapshot":
            return {"ok": True, "data": {"accounts": self._mock_accounts()}}
        if msg.op == "fetch_bars":
            sym = str(msg.payload.get("symbol") or "SPY").upper()
            return {
                "ok": True,
                "data": {
                    "bars": [
                        {"symbol": sym, "close": self._prices.get(sym, 100.0), "ts": time.time()},
                    ]
                },
            }
        return {"ok": False, "error": f"mock_unsupported_op:{msg.op}"}

    def _mock_accounts(self) -> List[Dict[str, Any]]:
        rows = []
        for slot in self._settings.slots:
            rows.append({"account_id": slot.account_id, "slot": slot.slot, "connected": True})
        if not rows:
            rows.append({"account_id": "mock", "slot": "host", "connected": True})
        return rows

    async def _tick_loop(self, stop: asyncio.Event) -> None:
        symbols = list(self._settings.watchlist_symbols) or list(self._prices.keys())
        while not stop.is_set():
            for sym in symbols:
                base = self._prices.get(sym, 100.0)
                base *= 1 + random.uniform(-0.002, 0.002)
                self._prices[sym] = base
                spread = max(0.01, round(base * 0.0005, 2))
                bid = round(base - spread, 2)
                ask = round(base + spread, 2)
                payload = {
                    "bid": bid,
                    "ask": ask,
                    "last": round(base, 2),
                    "mid": round((bid + ask) / 2, 4),
                    "ts": time.time(),
                    "contract_key": sym,
                    "symbol": sym,
                    "sec_type": "STK",
                }
                self._writer.write_tick(sym, payload)
            self._writer.set_subscriptions(set(symbols))
            self._writer.write_account_snapshot(
                {
                    "host_connected": True,
                    "secondary_connected": len(self._settings.slots) > 1,
                    "accounts_snapshot": self._mock_accounts(),
                    "mode": "mock",
                }
            )
            await asyncio.sleep(5)

    async def _health_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            now = time.time()
            common = {
                "connected": True,
                "mode": "mock",
                "client_id": _MOCK_CLIENT_ID,
                "last_msg_ts": now,
                "msg_count": 0,
                "reconnects": 0,
            }
            self._writer.write_ingestor_health({**common, "host_connected": True})
            self._writer.write_account_health(
                {
                    **common,
                    "host_connected": True,
                    "host_client_id": _MOCK_CLIENT_ID,
                    "secondary_connected": len(self._settings.slots) > 1,
                }
            )
            self._writer.write_operator_health({**common, "cmd_count": self._cmd_count})
            for slot in self._settings.slots:
                self._writer.write_plugin_health(slot.account_id, "connected", {"mode": "mock", "slot": slot.slot})
            await asyncio.sleep(10)
