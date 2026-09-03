"""Snapshot-stale self-heal ladder (L0 soft reconnect)."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bifrost_plugin.ib_gateway.connection import ConnectionState
from bifrost_plugin.ib_gateway.live import LiveGateway
from bifrost_plugin.ib_gateway.redis_keys import IB_ACCOUNT_SNAPSHOT_KEY, IB_GATEWAY_SELF_HEAL_KEY
from bifrost_plugin.ib_gateway.settings import GatewaySettings, TwsSlotConfig


def _live_gateway() -> LiveGateway:
    settings = GatewaySettings(
        mode="live",
        self_heal_enabled=True,
        snapshot_stale_reconnect_sec=90.0,
        snapshot_stale_max_before_rollout=3,
        soft_reconnect_cooldown_sec=60.0,
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
    )
    writer = MagicMock()
    writer.redis = MagicMock()
    writer.read_self_heal_enabled.return_value = True
    gw = LiveGateway(settings, writer)
    host = gw._slots["host"]
    host.state = ConnectionState.CONNECTED
    return gw


@pytest.mark.asyncio
async def test_self_heal_skips_when_snapshot_fresh() -> None:
    gw = _live_gateway()
    now = time.time()
    gw._writer.redis.get.return_value = json.dumps({"updated_at": now})
    gw.disconnect_all = AsyncMock()
    gw.reconnect_all = AsyncMock()
    await gw._maybe_self_heal_snapshot_stale(host_ok=True)
    gw.disconnect_all.assert_not_awaited()
    gw.reconnect_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_heal_soft_reconnect_when_stale() -> None:
    gw = _live_gateway()
    stale_ts = time.time() - 200
    gw._writer.redis.get.return_value = json.dumps({"updated_at": stale_ts})
    gw.disconnect_all = AsyncMock()
    gw.reconnect_all = AsyncMock()
    await gw._maybe_self_heal_snapshot_stale(host_ok=True)
    gw.disconnect_all.assert_awaited_once()
    gw.reconnect_all.assert_awaited_once()
    assert gw._self_heal_stale_streak == 1
    gw._writer.write_self_heal_status.assert_called()
    call_kw = gw._writer.write_self_heal_status.call_args.kwargs
    assert call_kw["last_action"] == "soft_reconnect"
    assert call_kw["rollout_recommended"] is False


@pytest.mark.asyncio
async def test_self_heal_cooldown_blocks_repeat() -> None:
    gw = _live_gateway()
    stale_ts = time.time() - 200
    gw._writer.redis.get.return_value = json.dumps({"updated_at": stale_ts})
    gw.disconnect_all = AsyncMock()
    gw.reconnect_all = AsyncMock()
    gw._self_heal_cooldown_until = time.time() + 120
    await gw._maybe_self_heal_snapshot_stale(host_ok=True)
    gw.disconnect_all.assert_not_awaited()
    gw.reconnect_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_heal_rollout_recommended_after_streak(monkeypatch) -> None:
    gw = _live_gateway()
    stale_ts = time.time() - 200
    gw._writer.redis.get.return_value = json.dumps({"updated_at": stale_ts})
    gw.disconnect_all = AsyncMock()
    gw.reconnect_all = AsyncMock()
    gw._self_heal_stale_streak = 2
    monkeypatch.setattr("bifrost_plugin.ib_gateway.live.os._exit", lambda _code: None)
    monkeypatch.setattr("bifrost_plugin.ib_gateway.live.asyncio.sleep", AsyncMock())
    await gw._maybe_self_heal_snapshot_stale(host_ok=True)
    call_kw = gw._writer.write_self_heal_status.call_args.kwargs
    assert call_kw["stale_streak"] == 3
    assert call_kw["rollout_recommended"] is True


@pytest.mark.asyncio
async def test_self_heal_pod_restart_when_still_stale_after_streak(monkeypatch) -> None:
    gw = _live_gateway()
    stale_ts = time.time() - 200
    gw._writer.redis.get.return_value = json.dumps({"updated_at": stale_ts})
    gw.disconnect_all = AsyncMock()
    gw.reconnect_all = AsyncMock()
    gw._self_heal_stale_streak = 2
    exit_calls: list[int] = []
    monkeypatch.setattr("bifrost_plugin.ib_gateway.live.os._exit", exit_calls.append)
    monkeypatch.setattr("bifrost_plugin.ib_gateway.live.asyncio.sleep", AsyncMock())
    await gw._maybe_self_heal_snapshot_stale(host_ok=True)
    assert exit_calls == [1]
    gw.disconnect_all.assert_awaited_once()
    gw.reconnect_all.assert_awaited_once()
    call_kw = gw._writer.write_self_heal_status.call_args.kwargs
    assert call_kw["last_action"] == "pod_restart_escalation"


def test_writer_self_heal_key_contract() -> None:
    assert IB_GATEWAY_SELF_HEAL_KEY == "ib:control:gateway_self_heal"
    assert IB_ACCOUNT_SNAPSHOT_KEY == "ib:account:snapshot:v1"
