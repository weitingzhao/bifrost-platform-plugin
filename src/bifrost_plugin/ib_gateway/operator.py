"""Redis Stream operator consumer."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from redis.exceptions import ResponseError

from bifrost_plugin.ib_gateway.protocol import CommandMessage, dumps_result, parse_stream_fields, result_key
from bifrost_plugin.ib_gateway.redis_keys import (
    IB_OPERATOR_CMD_STREAM,
    IB_OPERATOR_CONSUMER_GROUP,
    IB_OPERATOR_RESULT_PREFIX,
)
from bifrost_plugin.ib_gateway.writer import GatewayRedisWriter

logger = logging.getLogger(__name__)

Handler = Callable[[CommandMessage], Awaitable[Dict[str, Any]]]


def consumer_name() -> str:
    return f"ib-gateway-{socket.gethostname()}"


def ensure_stream_and_group(rds: Any, stream: str, group: str) -> None:
    try:
        rds.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info("Created consumer group %s on %s", group, stream)
    except Exception as e:
        if "busygroup" in str(e).lower():
            return
        raise


async def operator_loop(
    rds: Any,
    writer: GatewayRedisWriter,
    handler: Handler,
    *,
    stop: asyncio.Event,
    block_ms: int = 5000,
) -> None:
    stream = IB_OPERATOR_CMD_STREAM
    group = IB_OPERATOR_CONSUMER_GROUP
    consumer = consumer_name()
    ensure_stream_and_group(rds, stream, group)

    while not stop.is_set():
        try:
            reply = await asyncio.to_thread(
                rds.xreadgroup,
                group,
                consumer,
                {stream: ">"},
                count=10,
                block=block_ms,
            )
        except ResponseError as e:
            if "nogroup" in str(e).lower():
                ensure_stream_and_group(rds, stream, group)
                continue
            logger.warning("xreadgroup error: %s", e)
            await asyncio.sleep(1)
            continue
        except Exception as e:
            logger.warning("operator read: %s", e)
            await asyncio.sleep(1)
            continue

        for _stream_name, entries in reply or []:
            for entry_id, fields in entries:
                await _process_entry(rds, writer, handler, stream, group, entry_id, fields)


async def _process_entry(
    rds: Any,
    writer: GatewayRedisWriter,
    handler: Handler,
    stream: str,
    group: str,
    entry_id: str,
    fields: Any,
) -> None:
    fd: Dict[str, str] = {}
    if isinstance(fields, dict):
        fd = {str(k): v if isinstance(v, str) else str(v) for k, v in fields.items()}
    msg, err = parse_stream_fields(fd, stream_id=entry_id)
    if msg is None:
        logger.warning("bad operator cmd %s: %s", entry_id, err)
        await asyncio.to_thread(rds.xack, stream, group, entry_id)
        return
    if msg.is_expired():
        envelope = {"ok": False, "error": "deadline_expired", "req_id": msg.req_id}
    else:
        try:
            data = await handler(msg)
            envelope = {"ok": data.get("ok", False), "req_id": msg.req_id, **data}
        except Exception as e:
            logger.exception("operator execute %s", msg.op)
            envelope = {"ok": False, "error": str(e), "req_id": msg.req_id}
    raw, enc_err = dumps_result(envelope)
    if raw is None:
        envelope = {"ok": False, "error": enc_err or "encode_failed", "req_id": msg.req_id}
        raw, _ = dumps_result(envelope)
    if raw:
        writer.write_operator_result(msg.req_id, envelope if isinstance(envelope, dict) else {"raw": raw})
    await asyncio.to_thread(rds.xack, stream, group, entry_id)
