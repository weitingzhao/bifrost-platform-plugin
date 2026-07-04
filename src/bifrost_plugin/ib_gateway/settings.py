"""Gateway settings from YAML + environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

TWS_PORTS = {"tws_live": 7496, "tws_paper": 7497, "gateway_live": 4001, "gateway_paper": 4002}


@dataclass(frozen=True)
class TwsSlotConfig:
    slot: str  # host | secondary
    account_id: str
    ip: str
    port: int
    client_ids: Tuple[int, ...] = (1, 2)
    has_market_data: bool = False


@dataclass
class GatewaySettings:
    mode: str = "mock"
    redis_host: str = "redis-ib.data.svc.cluster.local"
    redis_port: int = 6379
    redis_username: str = "ib-gateway"
    redis_password: str = ""
    redis_db: int = 0
    slots: List[TwsSlotConfig] = field(default_factory=list)
    watchlist_symbols: Tuple[str, ...] = ("NVDA", "AAPL", "SPY", "QQQ", "TSLA")
    probe_interval_sec: float = 60.0
    health_ttl_sec: int = 30
    env_label: str = "platform"


def _resolve_redis_port(redis_raw: Dict[str, Any]) -> int:
    """Avoid K8s service-link env REDIS_IB_PORT=tcp://… — use explicit or YAML only."""
    explicit = os.environ.get("IB_GATEWAY_REDIS_PORT", "").strip()
    if explicit.isdigit():
        return int(explicit)
    raw_port = redis_raw.get("port", 6379)
    if isinstance(raw_port, int):
        return raw_port
    s = str(raw_port).strip()
    return int(s) if s.isdigit() else 6379


def _resolve_redis_host(redis_raw: Dict[str, Any]) -> str:
    explicit = os.environ.get("IB_GATEWAY_REDIS_HOST", "").strip()
    if explicit:
        return explicit
    return str(redis_raw.get("host") or "redis-ib.data.svc.cluster.local")


def _port_from_type(port_type: str) -> int:
    return TWS_PORTS.get(port_type.strip(), 7496)


def load_settings(path: str | None = None) -> GatewaySettings:
    cfg_path = path or os.environ.get("IB_GATEWAY_CONFIG", "/config/gateway.yaml")
    raw: Dict[str, Any] = {}
    p = Path(cfg_path)
    if p.is_file():
        with p.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    mode = os.environ.get("IB_GATEWAY_MODE", raw.get("mode", "mock")).strip().lower()
    redis_raw = raw.get("redis") or {}
    ib_raw = raw.get("ib") or {}

    settings = GatewaySettings(
        mode=mode,
        redis_host=_resolve_redis_host(redis_raw),
        redis_port=_resolve_redis_port(redis_raw),
        redis_username=os.environ.get("REDIS_IB_USER", redis_raw.get("username", "ib-gateway")),
        redis_password=os.environ.get("REDIS_IB_PASSWORD") or str(redis_raw.get("password") or ""),
        redis_db=int(redis_raw.get("db", 0)),
        probe_interval_sec=float(raw.get("probe_interval_sec", 60)),
        health_ttl_sec=int(raw.get("health_ttl_sec", 30)),
        env_label=os.environ.get("IB_GATEWAY_ENV", raw.get("env", "platform")),
    )

    wl = raw.get("watchlist_symbols") or os.environ.get("IB_GATEWAY_WATCHLIST", "")
    if isinstance(wl, list):
        settings.watchlist_symbols = tuple(str(s).strip().upper() for s in wl if str(s).strip())
    elif isinstance(wl, str) and wl.strip():
        settings.watchlist_symbols = tuple(s.strip().upper() for s in wl.split(",") if s.strip())

    for slot_name, has_md in (("host", True), ("secondary", False)):
        block = ib_raw.get(slot_name) or {}
        if not block:
            continue
        ip = str(block.get("ip") or "").strip()
        if not ip:
            continue
        port = int(block.get("port") or _port_from_type(str(block.get("port_type") or "tws_live")))
        account_id = str(block.get("account") or block.get("account_id") or slot_name).strip()
        cids = block.get("client_ids") or [1, 2]
        if isinstance(cids, int):
            cids = [cids]
        client_ids = tuple(int(x) for x in cids)
        settings.slots.append(
            TwsSlotConfig(
                slot=slot_name,
                account_id=account_id,
                ip=ip,
                port=port,
                client_ids=client_ids,
                has_market_data=has_md if slot_name == "host" else bool(block.get("has_market_data", False)),
            )
        )

    return settings
