"""SlotConnection client-id conflict detection + ghost-session sync."""

from __future__ import annotations

from bifrost_plugin.ib_gateway.connection import ConnectionState, SlotConnection
from bifrost_plugin.ib_gateway.settings import TwsSlotConfig


def test_client_id_conflict_detection() -> None:
    assert SlotConnection._is_client_id_conflict(
        "TimeoutError()",
        "Error 326, reqId -1: Unable to connect as the client id is already in use.",
    )
    assert SlotConnection._is_client_id_conflict(None, "client id is already in use")
    assert not SlotConnection._is_client_id_conflict("connection refused", None)


def test_sync_connection_state_clears_ghost() -> None:
    cfg = TwsSlotConfig(
        slot="host",
        account_id="U1",
        ip="127.0.0.1",
        port=7496,
        client_ids=(70, 71),
        has_market_data=True,
    )
    sc = SlotConnection(cfg)
    sc.state = ConnectionState.CONNECTED
    sc.ib = None
    assert sc.sync_connection_state() is False
    assert sc.state == ConnectionState.DISCONNECTED


class _FakeIB:
    def __init__(self, connected: bool) -> None:
        self._connected = connected

    def isConnected(self) -> bool:
        return self._connected


def test_sync_connection_state_respects_is_connected() -> None:
    cfg = TwsSlotConfig(
        slot="host",
        account_id="U1",
        ip="127.0.0.1",
        port=7496,
        client_ids=(70, 71),
        has_market_data=True,
    )
    sc = SlotConnection(cfg)
    sc.state = ConnectionState.CONNECTED
    sc.ib = _FakeIB(False)
    assert sc.sync_connection_state() is False
    assert sc.state == ConnectionState.DISCONNECTED

    sc.state = ConnectionState.CONNECTED
    sc.ib = _FakeIB(True)
    assert sc.sync_connection_state() is True
    assert sc.state == ConnectionState.CONNECTED
