"""CLI entry for ib-gateway console script."""

from __future__ import annotations

import asyncio
import logging

from bifrost_plugin.ib_gateway.app import run_gateway
from bifrost_plugin.ib_gateway.settings import load_settings


class DropAccountEcho(logging.Filter):
    """Drop ib_insync's INFO echo of every position / portfolio callback.

    It was ~99% of this pod's log volume (~13 lines/s of account contents) and
    kept the node's promtail CPU-throttled. Other wrapper INFO lines (TWS farm
    and connectivity codes such as 2104 / 2110 / 2151) and all errors are kept.
    """

    _PREFIXES = ("position: ", "updatePortfolio: ")

    def filter(self, record: logging.LogRecord) -> bool:
        return not (
            record.levelno <= logging.INFO
            and isinstance(record.msg, str)
            and record.msg.startswith(self._PREFIXES)
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )
    logging.getLogger("ib_insync.wrapper").addFilter(DropAccountEcho())
    asyncio.run(run_gateway(load_settings()))


if __name__ == "__main__":
    main()
