"""ib_insync position / portfolio echo is dropped; diagnostics are kept."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from bifrost_plugin.ib_gateway import app
from bifrost_plugin.ib_gateway.log_filters import (
    IB_INSYNC_WRAPPER_LOGGER,
    DropAccountEcho,
    install_log_filters,
)


def _record(level: int, msg: str) -> logging.LogRecord:
    return logging.LogRecord(IB_INSYNC_WRAPPER_LOGGER, level, __file__, 1, msg, None, None)


def _installed() -> list[logging.Filter]:
    wrapper = logging.getLogger(IB_INSYNC_WRAPPER_LOGGER)
    return [f for f in wrapper.filters if isinstance(f, DropAccountEcho)]


@pytest.fixture(autouse=True)
def _clean_wrapper_filters():
    wrapper = logging.getLogger(IB_INSYNC_WRAPPER_LOGGER)
    for f in _installed():
        wrapper.removeFilter(f)
    yield
    for f in _installed():
        wrapper.removeFilter(f)


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


def test_install_is_idempotent() -> None:
    install_log_filters()
    install_log_filters()
    assert len(_installed()) == 1


async def test_run_gateway_installs_the_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    # The image starts scripts/run_ib_gateway.py, which calls run_gateway but
    # not runner.main; the filter has to come from run_gateway itself.
    class _Stop(Exception):
        pass

    def _boom(_settings):
        raise _Stop

    monkeypatch.setattr(app, "make_redis", _boom)
    with pytest.raises(_Stop):
        await app.run_gateway(MagicMock())
    assert len(_installed()) == 1
