"""IB operator RPC helpers — ib_insync implementations for Platform Gateway live mode."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BAR_SIZE_MAP: Dict[str, str] = {
    "1 d": "1 day",
    "1 day": "1 day",
    "1 min": "1 min",
    "5 mins": "5 mins",
    "1 hour": "1 hour",
    "1 h": "1 hour",
}


def convert_ib_bars(bars: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for bar in bars or []:
        t = getattr(bar, "date", None)
        ts: Optional[float] = None
        bar_date_str: Optional[str] = None
        if t is None:
            continue
        if hasattr(t, "timestamp"):
            ts = float(t.timestamp())
            bar_date_str = str(t)[:10]
        else:
            try:
                ts = datetime.fromisoformat(str(t)).timestamp()
                bar_date_str = str(t)[:10]
            except Exception:
                continue
        entry: Dict[str, Any] = {
            "bar_time": ts,
            "open": float(getattr(bar, "open", 0) or 0),
            "high": float(getattr(bar, "high", 0) or 0),
            "low": float(getattr(bar, "low", 0) or 0),
            "close": float(getattr(bar, "close", 0) or 0),
            "volume": float(getattr(bar, "volume", 0) or 0),
        }
        if bar_date_str:
            entry["date"] = bar_date_str
        out.append(entry)
    return out


async def fetch_bars_range(
    ib: Any,
    symbol: str,
    period: str,
    *,
    start_ts: Optional[float] = None,
    end_ts: Optional[float] = None,
    interval_sec: Optional[float] = None,
) -> List[Dict[str, Any]]:
    from ib_insync import Stock  # noqa: PLC0415

    sym = (symbol or "").strip().upper()
    if not sym:
        return []
    per = (period or "1 D").strip()
    bar_setting = BAR_SIZE_MAP.get(per.lower(), "1 day")

    one_day = 24 * 60 * 60
    if bar_setting == "1 day":
        chunk_seconds = 365 * one_day
        duration_str = "1 Y"
    elif bar_setting in ("1 hour", "5 mins"):
        chunk_seconds = 7 * one_day
        duration_str = "1 W"
    elif bar_setting == "1 min":
        chunk_seconds = one_day
        duration_str = "1 D"
    else:
        chunk_seconds = 7 * one_day
        duration_str = "1 W"

    end_ts_eff = float(end_ts) if end_ts is not None else datetime.now(tz=timezone.utc).timestamp()
    start_ts_eff: Optional[float] = float(start_ts) if start_ts is not None else None

    stock = Stock(sym, "SMART", "USD")
    await ib.qualifyContractsAsync(stock)

    use_rth = bar_setting != "1 day"
    all_out: List[Dict[str, Any]] = []
    cur_end = end_ts_eff
    loops = 0

    while True:
        loops += 1
        if loops > 2000:
            logger.warning("fetch_bars_range: abort after %s loops %s", loops, sym)
            break

        if start_ts_eff is not None:
            if cur_end <= start_ts_eff:
                break
            seg_start = max(start_ts_eff, cur_end - chunk_seconds)
        else:
            seg_start = cur_end - chunk_seconds

        end_dt = datetime.fromtimestamp(cur_end, tz=timezone.utc)
        end_str = end_dt.strftime("%Y%m%d-%H:%M:%S")

        try:
            bars = await ib.reqHistoricalDataAsync(
                stock,
                endDateTime=end_str,
                durationStr=duration_str,
                barSizeSetting=bar_setting,
                whatToShow="TRADES",
                useRTH=use_rth,
                formatDate=2,
            )
        except Exception as e:
            logger.warning("fetch_bars_range chunk failed %s: %s", sym, e)
            break

        chunk_out = convert_ib_bars(bars)
        if not chunk_out:
            break
        all_out.extend(chunk_out)

        if interval_sec is not None and interval_sec > 0:
            await asyncio.sleep(interval_sec)
        elif loops >= 1:
            time.sleep(0.35)

        cur_end = seg_start
        if start_ts_eff is None:
            break

    return all_out


def _managed_account_ids(ib: Any) -> List[str]:
    try:
        raw = ib.managedAccounts()
    except Exception as e:
        logger.warning("managedAccounts: %s", e)
        return []
    if not raw:
        return []
    if isinstance(raw, str):
        parts = raw.split(",")
    else:
        parts = [str(s) for s in raw]
    return [s.strip() for s in parts if s.strip()]


def position_to_dict(pos: Any) -> Dict[str, Any]:
    c = pos.contract
    sec_type = getattr(c, "secType", "") or ""
    out: Dict[str, Any] = {
        "account": pos.account,
        "symbol": getattr(c, "symbol", "") or "",
        "secType": sec_type,
        "exchange": getattr(c, "exchange", "") or "",
        "currency": getattr(c, "currency", "") or "",
        "position": float(pos.position),
        "avgCost": float(pos.avgCost) if pos.avgCost is not None else None,
    }
    if sec_type == "OPT":
        out["lastTradeDateOrContractMonth"] = getattr(c, "lastTradeDateOrContractMonth", None) or ""
        out["strike"] = getattr(c, "strike", None)
        out["right"] = getattr(c, "right", None) or ""
        out["multiplier"] = getattr(c, "multiplier", None)
    return out


async def fetch_accounts_snapshot_rows(ib: Any) -> List[Dict[str, Any]]:
    """Return account summary + positions for all managed accounts on this IB session."""
    if not getattr(ib, "isConnected", lambda: False)():
        return []
    account_ids = _managed_account_ids(ib)
    if not account_ids:
        return []
    try:
        await ib.reqPositionsAsync()
        all_positions = list(ib.positions())
    except Exception as e:
        logger.warning("reqPositionsAsync: %s", e)
        all_positions = []

    out: List[Dict[str, Any]] = []
    for aid in account_ids:
        summary: Dict[str, Any] = {}
        try:
            values = await ib.accountSummaryAsync(aid)
            for v in values or []:
                tag = getattr(v, "tag", None)
                val = getattr(v, "value", None)
                if tag and val is not None:
                    summary[str(tag)] = val
        except Exception as e:
            logger.warning("accountSummaryAsync %s: %s", aid, e)
        if aid:
            summary["account"] = aid
        acct_positions = [p for p in all_positions if getattr(p, "account", None) == aid]
        out.append(
            {
                "account_id": aid,
                "summary": summary,
                "positions": [position_to_dict(p) for p in acct_positions],
            }
        )
    return out


async def fetch_executions(ib: Any, *, days: int = 7, account: Optional[str] = None) -> List[Dict[str, Any]]:
    from ib_insync import ExecutionFilter, Fill  # noqa: PLC0415

    time_str = ""
    if days > 0:
        start = datetime.now(timezone.utc) - timedelta(days=days - 1)
        time_str = start.strftime("%Y%m%d %H:%M:%S") + " UTC"
    ef = ExecutionFilter(acctCode=account or "", time=time_str)

    commission_by_exec_id: Dict[str, Dict[str, Any]] = {}

    def on_commission_report(_trade: Any, fill: Any, report: Any) -> None:
        if fill and getattr(fill, "execution", None) and report:
            eid = getattr(fill.execution, "execId", None)
            if eid:
                commission_by_exec_id[eid] = {
                    "commission": getattr(report, "commission", None),
                    "realizedPNL": getattr(report, "realizedPNL", None),
                    "currency": getattr(report, "currency", None),
                }

    ib.commissionReportEvent += on_commission_report
    try:
        fills = await ib.reqExecutionsAsync(ef)
        await asyncio.sleep(3.0)
    finally:
        ib.commissionReportEvent -= on_commission_report

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for fill in fills or []:
        if not isinstance(fill, Fill):
            continue
        ex = getattr(fill, "execution", None)
        contract = getattr(fill, "contract", None)
        exec_id = ex.execId if ex else None
        if exec_id and exec_id in seen:
            continue
        if exec_id:
            seen.add(exec_id)
        comm_report = getattr(fill, "commissionReport", None)
        commission = getattr(comm_report, "commission", None) if comm_report else None
        realized_pnl = getattr(comm_report, "realizedPNL", None) if comm_report else None
        if commission is None and exec_id and exec_id in commission_by_exec_id:
            rec = commission_by_exec_id[exec_id]
            commission = rec.get("commission")
            realized_pnl = realized_pnl if realized_pnl is not None else rec.get("realizedPNL")
        fill_time = getattr(fill, "time", None) or (ex.time if ex else None)
        ts = None
        if fill_time is not None:
            try:
                ts = fill_time.timestamp()
            except Exception:
                pass
        symbol = getattr(contract, "symbol", "") if contract else ""
        sec_type = getattr(contract, "secType", "") if contract else ""
        out.append(
            {
                "exec_id": exec_id,
                "account": ex.acctNumber if ex else None,
                "symbol": symbol,
                "sec_type": sec_type,
                "side": ex.side if ex else None,
                "shares": float(ex.shares) if ex and ex.shares is not None else None,
                "price": float(ex.price) if ex and ex.price is not None else None,
                "commission": float(commission) if commission is not None else None,
                "realized_pnl": float(realized_pnl) if realized_pnl is not None else None,
                "ts": ts,
            }
        )
    return out


async def fetch_option_expirations(ib: Any, symbol: str) -> Dict[str, Any]:
    from ib_insync import Stock  # noqa: PLC0415

    sym = (symbol or "").strip().upper()
    if not sym:
        return {"expirations": [], "strikes": [], "error": "missing_symbol"}
    stock = Stock(sym, "SMART", "USD")
    con_id = 0
    try:
        await ib.qualifyContractsAsync(stock)
        con_id = int(getattr(stock, "conId", 0) or 0)
    except Exception as e:
        logger.warning("fetch_option_expirations qualify %s: %s", sym, e)
    try:
        chains = await asyncio.wait_for(
            ib.reqSecDefOptParamsAsync(sym, "", "STK", con_id),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        return {"expirations": [], "strikes": [], "error": "timeout"}
    except Exception as e:
        return {"expirations": [], "strikes": [], "error": str(e)}

    expirations_set: set[str] = set()
    strikes_set: set[float] = set()
    for chain in chains or []:
        for e in getattr(chain, "expirations", []) or []:
            expirations_set.add(str(e).strip())
        for s in getattr(chain, "strikes", []) or []:
            try:
                strikes_set.add(float(s))
            except (TypeError, ValueError):
                pass
    return {"expirations": sorted(expirations_set), "strikes": sorted(strikes_set)}


async def fetch_underlying_price(ib: Any, symbol: str) -> Optional[float]:
    from ib_insync import Stock  # noqa: PLC0415

    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    stock = Stock(sym, "SMART", "USD")
    try:
        await ib.qualifyContractsAsync(stock)
        ticker = ib.reqMktData(stock, "", False, False)
        for _ in range(6):
            await asyncio.sleep(0.5)
            last = getattr(ticker, "last", None)
            if last is not None:
                try:
                    v = float(last)
                    if v > 0:
                        ib.cancelMktData(ticker)
                        return v
                except (TypeError, ValueError):
                    pass
        ib.cancelMktData(ticker)
    except Exception as e:
        logger.debug("fetch_underlying_price %s: %s", sym, e)
    return None


async def fetch_option_quote_one_shot(
    ib: Any,
    symbol: str,
    expiry: str,
    strike: float,
    right: str,
) -> Optional[Dict[str, Optional[float]]]:
    from ib_insync import Option  # noqa: PLC0415

    exp = (expiry or "").strip()
    rt = (right or "").upper()
    if not symbol or not exp or rt not in ("C", "P"):
        return None
    contract = Option(
        symbol=symbol.strip().upper(),
        lastTradeDateOrContractMonth=exp,
        strike=float(strike),
        right=rt,
        exchange="SMART",
        currency="USD",
    )
    ticker = None
    try:
        await ib.qualifyContractsAsync(contract)
        ticker = ib.reqMktData(contract, "", False, False)
        bid = ask = last = mid = None
        for _ in range(4):
            await asyncio.sleep(0.5)
            try:
                tbid = getattr(ticker, "bid", None)
                task = getattr(ticker, "ask", None)
                tlast = getattr(ticker, "last", None)
                if tbid is not None:
                    fb = float(tbid)
                    if fb > 0:
                        bid = fb
                if task is not None:
                    fa = float(task)
                    if fa > 0:
                        ask = fa
                if tlast is not None:
                    fl = float(tlast)
                    if fl > 0:
                        last = fl
            except (TypeError, ValueError):
                pass
            if bid is not None and ask is not None:
                mid = (bid + ask) / 2.0
            elif last is not None:
                mid = last
            if bid is not None or ask is not None or last is not None:
                break
        if bid is None and ask is None and last is None:
            return None
        return {"bid": bid, "ask": ask, "last": last, "mid": mid}
    except Exception as e:
        logger.debug("fetch_option_quote_one_shot %s: %s", symbol, e)
        return None
    finally:
        if ticker is not None:
            try:
                ib.cancelMktData(ticker)
            except Exception:
                pass


async def fetch_option_snapshot(
    ib: Any,
    symbol: str,
    expiration: str,
    strikes: List[float],
    *,
    max_contracts: int = 20,
    pacing_sec: float = 0.35,
) -> Tuple[List[Dict[str, Any]], Optional[float]]:
    underlying_price: Optional[float] = None
    if not strikes:
        underlying_price = await fetch_underlying_price(ib, symbol)

    filtered = list(strikes)
    if underlying_price is not None and underlying_price > 0:
        min_s = max(0.5, underlying_price * 0.01)
        max_s = underlying_price * 2.5
        filtered = [s for s in filtered if min_s <= s <= max_s]
    else:
        filtered = [s for s in filtered if s >= 5.0]

    max_strikes = min(max_contracts // 2, len(filtered)) if filtered else 0
    if max_strikes <= 0:
        return [], underlying_price

    if underlying_price is not None and filtered:
        selected = sorted(filtered, key=lambda s: abs(s - underlying_price))[:max_strikes]
    else:
        selected = filtered[:max_strikes]

    rows: List[Dict[str, Any]] = []
    for strike in selected:
        for right in ("C", "P"):
            quote = await fetch_option_quote_one_shot(ib, symbol, expiration, strike, right)
            row: Dict[str, Any] = {
                "strike": strike,
                "right": right,
                "bid": None,
                "ask": None,
                "last": None,
                "mid": None,
            }
            if quote:
                row.update(quote)
            rows.append(row)
            await asyncio.sleep(pacing_sec)
    return rows, underlying_price
