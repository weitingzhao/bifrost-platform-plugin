"""ib_insync position / portfolio echo is dropped; diagnostics are kept."""

from __future__ import annotations

import logging

from bifrost_plugin.ib_gateway.runner import DropAccountEcho


def _record(level: int, msg: str) -> logging.LogRecord:
    return logging.LogRecord("ib_insync.wrapper", level, __file__, 1, msg, None, None)


def test_drops_position_and_portfolio_echo() -> None:
    f = DropAccountEcho()
    assert not f.filter(_record(logging.INFO, "position: Position(account='U0000000', ...)"))
    assert not f.filter(_record(logging.INFO, "updatePortfolio: PortfolioItem(...)"))


def test_keeps_tws_status_codes_and_errors() -> None:
    f = DropAccountEcho()
    assert f.filter(
        _record(logging.INFO, "Warning 2104, reqId -1: Market data farm connection is OK:usfarm")
    )
    assert f.filter(
        _record(
            logging.INFO,
            "Warning 2110, reqId -1: Connectivity between Trader Workstation and server is broken.",
        )
    )
    assert f.filter(
        _record(logging.ERROR, "Error 1100, reqId -1: Connectivity between IBKR and TWS lost.")
    )


def test_keeps_a_position_line_logged_above_info() -> None:
    assert DropAccountEcho().filter(_record(logging.WARNING, "position: something odd"))
