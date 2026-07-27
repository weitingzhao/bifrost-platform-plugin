"""On-demand OPT control keys on redis-ib (Market Live → Gateway one-shot cache).

Mirrors bifrost_core.core.realtime.on_demand_opt without importing bifrost-core.
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional, Tuple

from bifrost_plugin.ib_gateway.redis_keys import (
    IB_OPTION_ON_DEMAND_SET,
    IB_OPTION_ON_DEMAND_TS,
    ON_DEMAND_OPT_DEFAULT_MAX_AGE_SEC,
)

logger = logging.getLogger(__name__)


def parse_opt_contract_key(
    contract_key: str,
) -> Optional[Tuple[str, str, float, str]]:
    """Parse ``SYMBOL|OPT|YYYYMMDD|STRIKE|RIGHT`` → (symbol, expiry, strike, right).

    Rejects malformed / non-OPT keys.
    """
    ck = (contract_key or "").strip()
    if not ck:
        return None
    parts = ck.split("|")
    if len(parts) != 5:
        return None
    sym, sec, expiry, strike_raw, right = parts
    sym = sym.strip().upper()
    sec = sec.strip().upper()
    expiry = expiry.strip()
    right = right.strip().upper()
    if not sym or sec != "OPT" or not expiry or right not in ("C", "P"):
        return None
    if not expiry.isdigit() or len(expiry) < 6:
        return None
    try:
        strike = float(strike_raw.strip())
    except (TypeError, ValueError):
        return None
    return sym, expiry, strike, right


def list_fresh_on_demand_opt(
    rds: Any,
    *,
    max_age_sec: float = ON_DEMAND_OPT_DEFAULT_MAX_AGE_SEC,
    now: Optional[float] = None,
) -> List[str]:
    """Return fresh on-demand OPT contract_keys; prune expired SET/HASH members."""
    if rds is None:
        return []
    ts_now = float(now if now is not None else time.time())
    try:
        members = rds.smembers(IB_OPTION_ON_DEMAND_SET) or set()
    except Exception as e:
        logger.warning("on_demand_opt SMEMBERS failed: %s", e)
        return []
    if not members:
        return []
    try:
        ts_map = rds.hgetall(IB_OPTION_ON_DEMAND_TS) or {}
    except Exception as e:
        logger.warning("on_demand_opt HGETALL failed: %s", e)
        ts_map = {}

    fresh: List[str] = []
    stale: List[str] = []
    for raw in members:
        ck = str(raw or "").strip()
        if not ck:
            continue
        raw_ts = ts_map.get(ck)
        if raw_ts is None and hasattr(ck, "encode"):
            raw_ts = ts_map.get(ck.encode())  # type: ignore[arg-type]
        try:
            last = float(raw_ts) if raw_ts is not None else 0.0
        except (TypeError, ValueError):
            last = 0.0
        if last > 0 and (ts_now - last) <= float(max_age_sec):
            fresh.append(ck)
        else:
            stale.append(ck)

    if stale:
        try:
            rds.srem(IB_OPTION_ON_DEMAND_SET, *stale)
            rds.hdel(IB_OPTION_ON_DEMAND_TS, *stale)
        except Exception as e:
            logger.warning("on_demand_opt prune failed: %s", e)

    fresh.sort()
    return fresh
