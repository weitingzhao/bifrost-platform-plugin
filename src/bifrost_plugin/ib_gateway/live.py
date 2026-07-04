"""Live IB Gateway — ib_insync connections to Host + Secondary TWS."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any, Dict, List, Optional

from bifrost_plugin.ib_gateway.connection import ConnectionState, SlotConnection
from bifrost_plugin.ib_gateway.protocol import CommandMessage
from bifrost_plugin.ib_gateway.settings import GatewaySettings, TwsSlotConfig
from bifrost_plugin.ib_gateway.writer import GatewayRedisWriter

logger = logging.getLogger(__name__)


def _float_or_none(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


class LiveGateway:
    def __init__(self, settings: GatewaySettings, writer: GatewayRedisWriter) -> None:
        self._settings = settings
        self._writer = writer
        self._slots: Dict[str, SlotConnection] = {
            s.slot: SlotConnection(s) for s in settings.slots
        }
        self._cmd_count = 0
        self._tickers: List[Any] = []

    def slot_for_payload(self, payload: Dict[str, Any]) -> Optional[SlotConnection]:
        slot_name = (payload.get("account_slot") or "primary").strip().lower()
        if slot_name in ("secondary", "sec"):
            return self._slots.get("secondary")
        return self._slots.get("host")

    async def run(self, stop: asyncio.Event) -> None:
        from ib_insync import IB, Stock  # noqa: PLC0415

        def _factory() -> IB:
            return IB()

        reconnect_tasks = [
            asyncio.create_task(
                sc.reconnect_loop(_factory, stop=stop),
                name=f"reconnect-{sc.cfg.slot}",
            )
            for sc in self._slots.values()
        ]
        market_task = asyncio.create_task(self._market_loop(stop), name="market")
        health_task = asyncio.create_task(self._health_loop(stop), name="health")
        await asyncio.gather(market_task, health_task, *reconnect_tasks)

    async def handle_command(self, msg: CommandMessage) -> Dict[str, Any]:
        self._cmd_count += 1
        if msg.op == "ping":
            return {"ok": True, "data": self.health_dict()}
        if msg.op == "fetch_accounts_snapshot":
            sc = self.slot_for_payload(msg.payload)
            if sc is None or sc.ib is None or sc.state != ConnectionState.CONNECTED:
                return {"ok": False, "error": "slot_not_connected"}
            accounts = [v for v in sc.ib.managedAccounts()]
            return {"ok": True, "data": {"accounts": [{"account_id": a} for a in accounts]}}
        if msg.op == "fetch_bars":
            host = self._slots.get("host")
            if host is None or host.ib is None or host.state != ConnectionState.CONNECTED:
                return {"ok": False, "error": "host_not_connected"}
            symbol = str(msg.payload.get("symbol") or "").strip().upper()
            if not symbol:
                return {"ok": False, "error": "missing_symbol"}
            period = str(msg.payload.get("period") or "1 day")
            duration = str(msg.payload.get("duration") or "1 D")
            contract = Stock(symbol, "SMART", "USD")
            bars = await host.ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=period,
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
            rows = [
                {
                    "date": str(b.date),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ]
            return {"ok": True, "data": {"bars": rows}}
        return {"ok": False, "error": f"unsupported_op:{msg.op}"}

    def health_dict(self) -> Dict[str, Any]:
        host = self._slots.get("host")
        sec = self._slots.get("secondary")
        return {
            "mode": "live",
            "cmd_count": self._cmd_count,
            "host_connected": host is not None and host.state == ConnectionState.CONNECTED,
            "secondary_connected": sec is not None and sec.state == ConnectionState.CONNECTED,
            "host_client_id": host.client_id if host else None,
            "secondary_client_id": sec.client_id if sec else None,
        }

    async def _market_loop(self, stop: asyncio.Event) -> None:
        from ib_insync import Stock  # noqa: PLC0415

        while not stop.is_set():
            host = self._slots.get("host")
            if host is None or host.ib is None or host.state != ConnectionState.CONNECTED:
                await asyncio.sleep(2)
                continue
            if not host.cfg.has_market_data:
                await asyncio.sleep(5)
                continue
            if not self._tickers:
                for sym in self._settings.watchlist_symbols:
                    contract = Stock(sym, "SMART", "USD")
                    ticker = host.ib.reqMktData(contract, "", False, False)
                    self._tickers.append((sym, ticker))
                self._writer.set_subscriptions(set(self._settings.watchlist_symbols))

            for sym, ticker in self._tickers:
                payload = {
                    "bid": _float_or_none(ticker.bid),
                    "ask": _float_or_none(ticker.ask),
                    "last": _float_or_none(ticker.last),
                    "mid": _float_or_none(ticker.midpoint()),
                    "ts": time.time(),
                    "contract_key": sym,
                    "symbol": sym,
                    "sec_type": "STK",
                }
                self._writer.write_tick(sym, payload)
                host.note_message()

            snap_accounts = []
            for sc in self._slots.values():
                if sc.ib and sc.state == ConnectionState.CONNECTED:
                    for acct in sc.ib.managedAccounts():
                        snap_accounts.append(
                            {
                                "account_id": acct,
                                "slot": sc.cfg.slot,
                                "summary": {},
                                "positions": [],
                            }
                        )
            self._writer.write_account_snapshot(
                {
                    "host_connected": host.state == ConnectionState.CONNECTED,
                    "secondary_connected": (
                        self._slots.get("secondary") is not None
                        and self._slots["secondary"].state == ConnectionState.CONNECTED
                    ),
                    "accounts_snapshot": snap_accounts,
                    "mode": "live",
                }
            )
            await asyncio.sleep(2)

    async def _health_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            now = time.time()
            host = self._slots.get("host")
            sec = self._slots.get("secondary")
            host_ok = host is not None and host.state == ConnectionState.CONNECTED
            sec_ok = sec is not None and sec.state == ConnectionState.CONNECTED
            self._writer.write_ingestor_health(
                {
                    "connected": host_ok,
                    "client_id": host.client_id if host else 0,
                    "last_msg_ts": host.last_message_at if host else 0,
                    "reconnects": host.reconnects if host else 0,
                    "mode": "live",
                }
            )
            self._writer.write_account_health(
                {
                    "host_connected": host_ok,
                    "host_client_id": host.client_id if host else 0,
                    "secondary_connected": sec_ok,
                    "secondary_client_id": sec.client_id if sec else 0,
                    "last_msg_ts": now,
                    "mode": "live",
                }
            )
            self._writer.write_operator_health({**self.health_dict(), "last_msg_ts": now})
            for sc in self._slots.values():
                st = "connected" if sc.state == ConnectionState.CONNECTED else sc.state.value
                self._writer.write_plugin_health(
                    sc.cfg.account_id,
                    st,
                    {"slot": sc.cfg.slot, "client_id": sc.client_id, "mode": "live"},
                )
            await asyncio.sleep(10)
