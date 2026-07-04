"""SlotConnection client-id conflict detection."""

from __future__ import annotations

from bifrost_plugin.ib_gateway.connection import SlotConnection


def test_client_id_conflict_detection() -> None:
    assert SlotConnection._is_client_id_conflict(
        "TimeoutError()",
        "Error 326, reqId -1: Unable to connect as the client id is already in use.",
    )
    assert SlotConnection._is_client_id_conflict(None, "client id is already in use")
    assert not SlotConnection._is_client_id_conflict("connection refused", None)
