"""IB Gateway application entry."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Union

import redis

from bifrost_plugin.ib_gateway.live import LiveGateway
from bifrost_plugin.ib_gateway.mock import MockGateway
from bifrost_plugin.ib_gateway.operator import operator_loop
from bifrost_plugin.ib_gateway.settings import GatewaySettings, load_settings
from bifrost_plugin.ib_gateway.writer import GatewayRedisWriter

logger = logging.getLogger(__name__)

GatewayEngine = Union[MockGateway, LiveGateway]


def make_redis(settings: GatewaySettings) -> redis.Redis:
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        username=settings.redis_username or None,
        password=settings.redis_password or None,
        decode_responses=True,
    )


async def run_gateway(settings: GatewaySettings | None = None) -> None:
    settings = settings or load_settings()
    rds = make_redis(settings)
    writer = GatewayRedisWriter(rds, env=settings.env_label)

    if settings.mode == "mock":
        engine: GatewayEngine = MockGateway(settings, writer)
        logger.info("IB Gateway starting in mock mode")
    else:
        engine = LiveGateway(settings, writer)
        logger.info("IB Gateway starting in live mode slots=%s", [s.slot for s in settings.slots])

    stop = asyncio.Event()

    def _stop(*_: object) -> None:
        logger.info("Shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _stop())

    tasks = [
        asyncio.create_task(engine.run(stop), name="engine"),
        asyncio.create_task(operator_loop(rds, writer, engine.handle_command, stop=stop), name="operator"),
    ]
    await stop.wait()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("IB Gateway stopped")
