"""Mock IB Gateway — no TWS socket; writes legacy-compatible redis-ib keys."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Dict, List

from bifrost_plugin.ib_gateway.protocol import CommandMessage, dumps_result
from bifrost_plugin.ib_gateway.settings import GatewaySettings
from bifrost_plugin.ib_gateway.redis_keys import stk_contract_key
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
        payload = msg.payload
        if msg.op == "ping":
            return {
                "ok": True,
                "data": {
                    "mode": "mock",
                    "cmd_count": self._cmd_count,
                    "slots": [s.slot for s in self._settings.slots],
                },
            }
        if msg.op == "disconnect_all":
            return {"ok": True, "data": {"mode": "mock", "disconnected": True}}
        if msg.op == "reconnect_all":
            return {"ok": True, "data": {"mode": "mock", "reconnected": True}}
        if msg.op == "fetch_accounts_snapshot":
            return {"ok": True, "data": {"accounts": self._mock_accounts()}}
        if msg.op == "fetch_executions":
            return {
                "ok": True,
                "data": {
                    "executions": [
                        {
                            "exec_id": "mock-1",
                            "symbol": "SPY",
                            "sec_type": "STK",
                            "side": "BOT",
                            "shares": 100.0,
                            "price": 560.0,
                            "ts": time.time(),
                        }
                    ]
                },
            }
        if msg.op == "fetch_bars":
            sym = str(payload.get("symbol") or "SPY").upper()
            return {
                "ok": True,
                "data": {
                    "bars": [
                        {"symbol": sym, "close": self._prices.get(sym, 100.0), "ts": time.time()},
                    ]
                },
            }
        if msg.op == "fetch_bars_range":
            sym = str(payload.get("symbol") or "SPY").upper()
            base = self._prices.get(sym, 100.0)
            now = time.time()
            return {
                "ok": True,
                "data": {
                    "bars": [
                        {
                            "bar_time": now - 86400,
                            "open": base - 1,
                            "high": base + 1,
                            "low": base - 2,
                            "close": base,
                            "volume": 1000000,
                            "date": "mock",
                        },
                        {
                            "bar_time": now,
                            "open": base,
                            "high": base + 0.5,
                            "low": base - 0.5,
                            "close": base + 0.25,
                            "volume": 900000,
                            "date": "mock",
                        },
                    ]
                },
            }
        if msg.op == "fetch_option_expirations":
            sym = str(payload.get("symbol") or "NVDA").upper()
            return {
                "ok": True,
                "data": {
                    "expirations": ["20260718", "20260815"],
                    "strikes": [120.0, 130.0, 140.0],
                    "symbol": sym,
                },
            }
        if msg.op == "fetch_option_snapshot":
            sym = str(payload.get("symbol") or "NVDA").upper()
            exp = str(payload.get("expiration") or "20260718")
            return {
                "ok": True,
                "data": {
                    "underlying_price": self._prices.get(sym, 130.0),
                    "rows": [
                        {
                            "strike": 130.0,
                            "right": "C",
                            "bid": 5.1,
                            "ask": 5.3,
                            "last": 5.2,
                            "mid": 5.2,
                            "symbol": sym,
                            "expiration": exp,
                        },
                        {
                            "strike": 130.0,
                            "right": "P",
                            "bid": 4.8,
                            "ask": 5.0,
                            "last": 4.9,
                            "mid": 4.9,
                            "symbol": sym,
                            "expiration": exp,
                        },
                    ],
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
                contract_key = stk_contract_key(sym)
                payload = {
                    "bid": bid,
                    "ask": ask,
                    "last": round(base, 2),
                    "mid": round((bid + ask) / 2, 4),
                    "ts": time.time(),
                    "contract_key": contract_key,
                    "symbol": sym,
                    "sec_type": "STK",
                }
                self._writer.write_tick(contract_key, payload)
            self._writer.set_subscriptions({stk_contract_key(sym) for sym in symbols})
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
