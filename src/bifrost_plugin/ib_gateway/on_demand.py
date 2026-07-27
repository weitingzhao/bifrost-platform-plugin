"""On-demand STK control keys on redis-ib (Market Live → Gateway Host MD).

Mirrors bifrost_core.core.realtime.on_demand_stk without importing bifrost-core
(plugin stays a thin IB edge dependency).
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional, Sequence, Set, Tuple

from bifrost_plugin.ib_gateway.redis_keys import (
    IB_INGESTER_ON_DEMAND_STK,
    IB_INGESTER_ON_DEMAND_STK_TS,
    ON_DEMAND_STK_DEFAULT_MAX_AGE_SEC,
)

logger = logging.getLogger(__name__)


def list_fresh_on_demand_stk(
    rds: Any,
    *,
    max_age_sec: float = ON_DEMAND_STK_DEFAULT_MAX_AGE_SEC,
    now: Optional[float] = None,
) -> List[str]:
    """Return fresh on-demand symbols; prune expired SET/HASH members."""
    if rds is None:
        return []
    ts_now = float(now if now is not None else time.time())
    try:
        members = rds.smembers(IB_INGESTER_ON_DEMAND_STK) or set()
    except Exception as e:
        logger.warning("on_demand SMEMBERS failed: %s", e)
        return []
    if not members:
        return []
    try:
        ts_map = rds.hgetall(IB_INGESTER_ON_DEMAND_STK_TS) or {}
    except Exception as e:
        logger.warning("on_demand HGETALL failed: %s", e)
        ts_map = {}

    fresh: List[str] = []
    stale: List[str] = []
    for raw in members:
        sym = str(raw or "").strip().upper()
        if not sym:
            continue
        raw_ts = ts_map.get(sym)
        if raw_ts is None and hasattr(sym, "encode"):
            raw_ts = ts_map.get(sym.encode())  # type: ignore[arg-type]
        try:
            last = float(raw_ts) if raw_ts is not None else 0.0
        except (TypeError, ValueError):
            last = 0.0
        if last > 0 and (ts_now - last) <= float(max_age_sec):
            fresh.append(sym)
        else:
            stale.append(sym)

    if stale:
        try:
            rds.srem(IB_INGESTER_ON_DEMAND_STK, *stale)
            rds.hdel(IB_INGESTER_ON_DEMAND_STK_TS, *stale)
        except Exception as e:
            logger.warning("on_demand prune failed: %s", e)

    fresh.sort()
    return fresh


def build_desired_stk_symbols(
    watchlist: Sequence[str],
    on_demand: Sequence[str],
    *,
    max_stream_stk: int = 40,
) -> Tuple[List[str], bool]:
    """Merge watchlist + on-demand with hard cap (watchlist preferred).

    Returns (desired_symbols, truncated).
    """
    wl = [str(s).strip().upper() for s in watchlist if str(s).strip()]
    seen: Set[str] = set()
    desired: List[str] = []
    for sym in wl:
        if sym in seen:
            continue
        seen.add(sym)
        desired.append(sym)

    truncated = False
    cap = max(1, int(max_stream_stk))
    for sym in on_demand:
        s = str(sym).strip().upper()
        if not s or s in seen:
            continue
        if len(desired) >= cap:
            truncated = True
            break
        seen.add(s)
        desired.append(s)
    return desired, truncated
