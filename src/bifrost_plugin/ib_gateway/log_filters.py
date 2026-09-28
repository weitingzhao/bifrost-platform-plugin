"""Logging filters for the gateway process."""

from __future__ import annotations

import logging

IB_INSYNC_WRAPPER_LOGGER = "ib_insync.wrapper"


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


def install_log_filters() -> None:
    """Idempotent; called from run_gateway so every entrypoint gets it.

    The image runs scripts/run_ib_gateway.py, not the `ib-gateway` console
    script, so installing this in runner.main alone never reached production.
    """
    wrapper = logging.getLogger(IB_INSYNC_WRAPPER_LOGGER)
    if not any(isinstance(f, DropAccountEcho) for f in wrapper.filters):
        wrapper.addFilter(DropAccountEcho())
