"""CLI entry for ib-gateway console script."""

from __future__ import annotations

import asyncio
import logging

from bifrost_plugin.ib_gateway.app import run_gateway
from bifrost_plugin.ib_gateway.settings import load_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )
    asyncio.run(run_gateway(load_settings()))


if __name__ == "__main__":
    main()
