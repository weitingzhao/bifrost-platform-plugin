"""Per-env operator streams answer read ops only (debt TD-21)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from bifrost_plugin.ib_gateway import operator
from bifrost_plugin.ib_gateway.protocol import ALL_OPS, READ_ONLY_OPS, CommandMessage
from bifrost_plugin.ib_gateway.redis_keys import (
    IB_OPERATOR_CMD_STREAM,
    IB_OPERATOR_CONSUMER_GROUP,
    IB_OPERATOR_ENV_CMD_STREAMS,
)

DEV, STG = IB_OPERATOR_ENV_CMD_STREAMS


def test_env_streams_are_the_production_stream_suffixed() -> None:
    assert IB_OPERATOR_ENV_CMD_STREAMS == (IB_OPERATOR_CMD_STREAM + ":dev", IB_OPERATOR_CMD_STREAM + ":stg")


def test_read_only_ops_leave_out_the_connection_ops() -> None:
    assert set(ALL_OPS) - set(READ_ONLY_OPS) == {"disconnect_all", "reconnect_all"}


@pytest.mark.parametrize("op", ALL_OPS)
def test_production_stream_answers_every_op(op: str) -> None:
    assert operator.op_allowed_on_stream(op, IB_OPERATOR_CMD_STREAM)


@pytest.mark.parametrize("stream", IB_OPERATOR_ENV_CMD_STREAMS)
def test_env_stream_refuses_the_connection_ops(stream: str) -> None:
    for op in READ_ONLY_OPS:
        assert operator.op_allowed_on_stream(op, stream)
    assert not operator.op_allowed_on_stream("disconnect_all", stream)
    assert not operator.op_allowed_on_stream("reconnect_all", stream)


class _Writer:
    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}

    def write_operator_result(self, req_id: str, envelope: dict[str, Any]) -> None:
        self.results[req_id] = envelope


def _run_entry(stream: str, op: str) -> tuple[dict[str, Any], list[CommandMessage], MagicMock]:
    rds = MagicMock()
    writer = _Writer()
    seen: list[CommandMessage] = []

    async def handler(msg: CommandMessage) -> dict[str, Any]:
        seen.append(msg)
        return {"ok": True}

    fields = {"req_id": "r1", "op": op, "payload": "{}", "caller": "test"}
    asyncio.run(
        operator._process_entry(rds, writer, handler, stream, IB_OPERATOR_CONSUMER_GROUP, "1-0", fields)
    )
    return writer.results["r1"], seen, rds


def test_disconnect_on_an_env_stream_is_refused_and_acked() -> None:
    envelope, seen, rds = _run_entry(DEV, "disconnect_all")
    assert envelope == {"ok": False, "error": "op_not_allowed_on_stream:disconnect_all", "req_id": "r1"}
    assert seen == []
    rds.xack.assert_called_once_with(DEV, IB_OPERATOR_CONSUMER_GROUP, "1-0")


def test_read_op_on_an_env_stream_reaches_the_handler() -> None:
    envelope, seen, rds = _run_entry(STG, "fetch_executions")
    assert envelope["ok"] is True
    assert [m.op for m in seen] == ["fetch_executions"]
    rds.xack.assert_called_once_with(STG, IB_OPERATOR_CONSUMER_GROUP, "1-0")


def test_disconnect_on_the_production_stream_reaches_the_handler() -> None:
    envelope, seen, _ = _run_entry(IB_OPERATOR_CMD_STREAM, "disconnect_all")
    assert envelope["ok"] is True
    assert [m.op for m in seen] == ["disconnect_all"]


def test_loop_reads_all_three_streams_and_routes_each_entry_by_its_stream() -> None:
    stop = asyncio.Event()
    calls: list[dict[str, str]] = []
    rds = MagicMock()

    def xreadgroup(group: str, consumer: str, streams: dict[str, str], count: int, block: int) -> Any:
        calls.append(streams)
        stop.set()
        return [
            (DEV.encode(), [("1-0", {"req_id": "a", "op": "reconnect_all", "caller": "dev"})]),
            (IB_OPERATOR_CMD_STREAM, [("2-0", {"req_id": "b", "op": "reconnect_all", "caller": "prod"})]),
        ]

    rds.xreadgroup.side_effect = xreadgroup
    writer = _Writer()

    async def handler(msg: CommandMessage) -> dict[str, Any]:
        return {"ok": True}

    asyncio.run(operator.operator_loop(rds, writer, handler, stop=stop, block_ms=1))

    assert calls == [{IB_OPERATOR_CMD_STREAM: ">", DEV: ">", STG: ">"}]
    assert [c.args[0] for c in rds.xgroup_create.call_args_list] == [IB_OPERATOR_CMD_STREAM, DEV, STG]
    assert writer.results["a"]["ok"] is False
    assert writer.results["b"]["ok"] is True
