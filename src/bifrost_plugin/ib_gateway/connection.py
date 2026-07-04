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
        self._connect_lock = asyncio.Lock()

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

    @staticmethod
    def _is_client_id_conflict(*parts: Optional[str]) -> bool:
        text = " ".join(p for p in parts if p).lower()
        return "326" in text or "already in use" in text

    async def disconnect(self) -> None:
        async with self._connect_lock:
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

        async with self._connect_lock:
            if self.ib is not None and getattr(self.ib, "isConnected", lambda: False)():
                self.state = ConnectionState.CONNECTED
                return True

            if self.ib is not None:
                try:
                    self.ib.disconnect()
                except Exception:
                    pass
                self.ib = None

            self.state = ConnectionState.RECONNECTING

            for _ in range(len(self.cfg.client_ids)):
                cid = self.cfg.client_ids[self.current_cid_index]
                ib = factory()
                cid_conflict = False

                def _on_error(req_id: int, code: int, msg: str, contract: Any) -> None:
                    nonlocal cid_conflict
                    self.last_error = f"Error {code}, reqId {req_id}: {msg}"
                    if code == 326 or "already in use" in msg.lower():
                        cid_conflict = True

                ib.errorEvent += _on_error
                try:
                    await ib.connectAsync(self.cfg.ip, self.cfg.port, clientId=cid, timeout=30)
                    if cid_conflict or not ib.isConnected():
                        raise ConnectionError(self.last_error or "TWS rejected client id")
                    self.ib = ib
                    self.state = ConnectionState.CONNECTED
                    self.last_error = None
                    self.note_message()
                    logger.info(
                        "Connected slot=%s cid=%s host=%s:%s",
                        self.cfg.slot,
                        cid,
                        self.cfg.ip,
                        self.cfg.port,
                    )
                    return True
                except Exception as e:
                    err_text = str(e) or self.last_error or ""
                    self.last_error = err_text or self.last_error
                    logger.warning("Connect failed slot=%s cid=%s: %s", self.cfg.slot, cid, self.last_error)
                    if self._is_client_id_conflict(err_text, self.last_error) or cid_conflict:
                        self.current_cid_index = (self.current_cid_index + 1) % len(self.cfg.client_ids)
                        await asyncio.sleep(1)
                    try:
                        ib.disconnect()
                    except Exception:
                        pass
                finally:
                    ib.errorEvent -= _on_error

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
