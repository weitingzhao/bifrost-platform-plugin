"""TWS connection state machine with client-id failover."""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from typing import Any, Callable, Optional

from bifrost_plugin.ib_gateway.settings import TwsSlotConfig

logger = logging.getLogger(__name__)


class ConnectionState(enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    MAINTENANCE = "maintenance"


class SlotConnection:
    """One TWS slot — 1 active ib_insync IB session at a time."""

    def __init__(self, cfg: TwsSlotConfig) -> None:
        self.cfg = cfg
        self.state = ConnectionState.DISCONNECTED
        self.current_cid_index = 0
        self.ib: Any = None
        self.last_message_at = 0.0
        self.reconnects = 0
        self.last_error: Optional[str] = None
        self._maintenance = False

    @property
    def client_id(self) -> int:
        return self.cfg.client_ids[self.current_cid_index]

    def note_message(self) -> None:
        self.last_message_at = time.time()

    def enter_maintenance(self) -> None:
        self._maintenance = True
        self.state = ConnectionState.MAINTENANCE

    def exit_maintenance(self) -> None:
        self._maintenance = False

    async def disconnect(self) -> None:
        if self.ib is not None:
            try:
                self.ib.disconnect()
            except Exception as e:
                logger.debug("disconnect %s: %s", self.cfg.slot, e)
            self.ib = None
        self.state = ConnectionState.DISCONNECTED

    async def connect(self, factory: Callable[[], Any]) -> bool:
        if self._maintenance:
            return False
        self.state = ConnectionState.RECONNECTING
        from ib_insync import IB  # noqa: PLC0415

        for attempt in range(len(self.cfg.client_ids)):
            cid = self.cfg.client_ids[self.current_cid_index]
            ib = factory()
            try:
                await ib.connectAsync(self.cfg.ip, self.cfg.port, clientId=cid, timeout=30)
                self.ib = ib
                self.state = ConnectionState.CONNECTED
                self.last_error = None
                self.note_message()
                logger.info("Connected slot=%s cid=%s host=%s:%s", self.cfg.slot, cid, self.cfg.ip, self.cfg.port)
                return True
            except Exception as e:
                self.last_error = str(e)
                logger.warning("Connect failed slot=%s cid=%s: %s", self.cfg.slot, cid, e)
                if "client id is already in use" in str(e).lower() or "326" in str(e):
                    self.current_cid_index = (self.current_cid_index + 1) % len(self.cfg.client_ids)
                try:
                    ib.disconnect()
                except Exception:
                    pass
        self.state = ConnectionState.DISCONNECTED
        return False

    async def reconnect_loop(
        self,
        factory: Callable[[], Any],
        *,
        stop: asyncio.Event,
        base_delay: float = 5.0,
        max_delay: float = 60.0,
    ) -> None:
        delay = base_delay
        while not stop.is_set():
            if self._maintenance:
                await asyncio.sleep(2)
                continue
            if self.state == ConnectionState.CONNECTED:
                await asyncio.sleep(1)
                delay = base_delay
                continue
            ok = await self.connect(factory)
            if ok:
                self.reconnects += 1
                delay = base_delay
            else:
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
