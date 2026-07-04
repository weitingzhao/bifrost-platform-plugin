#!/usr/bin/env python3
"""Run Platform IB Gateway Plugin."""

from __future__ import annotations

import asyncio
import logging
import sys

from bifrost_plugin.ib_gateway.app import run_gateway
from bifrost_plugin.ib_gateway.settings import load_settings


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, (sys.argv[1] if len(sys.argv) > 1 else "INFO").upper(), logging.INFO),
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )
    settings = load_settings()
    asyncio.run(run_gateway(settings))


if __name__ == "__main__":
    main()
