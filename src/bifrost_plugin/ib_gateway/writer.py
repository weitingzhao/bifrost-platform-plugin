"""Redis writers for IB Gateway — legacy-compatible keys on redis-ib."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional, Set

from bifrost_plugin.ib_gateway.redis_keys import (
    IB_ACCOUNT_AGENT_HEALTH_KEY,
    IB_ACCOUNT_NOTIFY_CHANNEL,
    IB_ACCOUNT_SNAPSHOT_KEY,
    IB_ACCOUNT_STREAM_KEY,
    IB_ACCOUNT_STREAM_MAXLEN,
    IB_GATEWAY_HEALTH_PREFIX,
    IB_GATEWAY_SELF_HEAL_KEY,
    IB_INGESTER_CHANNEL,
    IB_INGESTER_HEALTH_KEY,
    IB_INGESTER_SUBSCRIPTIONS_KEY,
    IB_INGESTER_TICK_PREFIX,
    IB_INGESTER_TICK_TTL_SEC,
    IB_OPTION_CACHE_META_REFRESH_TS,
    IB_OPTION_CACHE_PREFIX,
    IB_OPTION_CACHE_TTL_SEC,
    IB_OPERATOR_HEALTH_KEY,
    IB_OPERATOR_RESULT_PREFIX,
    IB_OPERATOR_RESULT_TTL_SEC,
)

logger = logging.getLogger(__name__)


class GatewayRedisWriter:
    def __init__(self, rds: Any, *, env: str = "platform") -> None:
        self._rds = rds
        self._env = env
        self._account_version = 0

    def write_tick(self, contract_key: str, data: Dict[str, Any]) -> None:
        key = IB_INGESTER_TICK_PREFIX + contract_key
        self._rds.set(key, json.dumps(data, default=str), ex=IB_INGESTER_TICK_TTL_SEC)
        self._rds.publish(
            IB_INGESTER_CHANNEL,
            json.dumps({"contract_key": contract_key, "ts": data.get("ts")}, default=str),
        )

    def write_opt_cache(self, contract_key: str, data: Dict[str, Any]) -> None:
        """SET JSON at ``ib:option:cache:{contract_key}`` with TTL (OPT one-shot cache)."""
        ck = (contract_key or "").strip()
        if not ck:
            return
        key = IB_OPTION_CACHE_PREFIX + ck
        self._rds.set(key, json.dumps(data, default=str), ex=IB_OPTION_CACHE_TTL_SEC)

    def set_opt_cache_last_refresh_ts(self, ts: Optional[float] = None) -> None:
        """Mark OPT cache loop completion for health/observability."""
        value = str(float(ts if ts is not None else time.time()))
        self._rds.set(IB_OPTION_CACHE_META_REFRESH_TS, value)

    def set_subscriptions(self, keys: Set[str]) -> None:
        pipe = self._rds.pipeline()
        pipe.delete(IB_INGESTER_SUBSCRIPTIONS_KEY)
        if keys:
            pipe.sadd(IB_INGESTER_SUBSCRIPTIONS_KEY, *sorted(keys))
        pipe.execute()

    @property
    def redis(self) -> Any:
        """Raw redis-ib client (on-demand control reads)."""
        return self._rds

    def write_ingestor_health(self, fields: Dict[str, Any]) -> None:
        self._write_hash(IB_INGESTER_HEALTH_KEY, {"env": self._env, "plugin": "ib-gateway", **fields})

    def write_account_health(self, fields: Dict[str, Any]) -> None:
        self._write_hash(IB_ACCOUNT_AGENT_HEALTH_KEY, {"env": self._env, "plugin": "ib-gateway", **fields})

    def write_operator_health(self, fields: Dict[str, Any]) -> None:
        self._write_hash(IB_OPERATOR_HEALTH_KEY, {"env": self._env, "plugin": "ib-gateway", **fields})

    def write_account_snapshot(self, payload: Dict[str, Any]) -> None:
        self._account_version += 1
        body = dict(payload)
        body["version"] = int(body.get("version") or self._account_version)
        body["updated_at"] = float(body.get("updated_at") or time.time())
        raw = json.dumps(body, separators=(",", ":"), default=str)
        self._rds.set(IB_ACCOUNT_SNAPSHOT_KEY, raw)
        self._rds.publish(IB_ACCOUNT_NOTIFY_CHANNEL, str(body["version"]))
        try:
            self._rds.xadd(
                IB_ACCOUNT_STREAM_KEY,
                {
                    "version": str(body["version"]),
                    "updated_at": str(body["updated_at"]),
                    "payload": raw,
                },
                maxlen=IB_ACCOUNT_STREAM_MAXLEN,
                approximate=True,
            )
        except Exception as e:
            logger.warning("account stream xadd failed: %s", e)

    def write_operator_result(self, req_id: str, envelope: Dict[str, Any]) -> None:
        key = IB_OPERATOR_RESULT_PREFIX + req_id
        self._rds.set(key, json.dumps(envelope, default=str), ex=IB_OPERATOR_RESULT_TTL_SEC)

    def write_self_heal_status(
        self,
        *,
        last_action: str,
        last_action_ts: float,
        stale_streak: int,
        cooldown_until: float,
        reason: str,
        self_heal_enabled: bool,
        rollout_recommended: bool = False,
        snapshot_age_sec: Optional[float] = None,
    ) -> None:
        """Publish L0 self-heal ladder state for platform-api / Console."""
        fields: Dict[str, Any] = {
            "last_action": last_action,
            "last_action_ts": last_action_ts,
            "stale_streak": stale_streak,
            "cooldown_until": cooldown_until,
            "reason": reason,
            "enabled": "true" if self_heal_enabled else "false",
            "rollout_recommended": "true" if rollout_recommended else "false",
            "updated_at": time.time(),
            "env": self._env,
        }
        if snapshot_age_sec is not None:
            fields["snapshot_age_sec"] = snapshot_age_sec
        self._write_hash(IB_GATEWAY_SELF_HEAL_KEY, fields)

    def read_self_heal_enabled(self) -> bool:
        """Runtime kill switch — platform-api may SET ``enabled`` on the self_heal hash."""
        try:
            raw = self._rds.hget(IB_GATEWAY_SELF_HEAL_KEY, "enabled")
            if raw is None:
                return True
            return str(raw).strip().lower() in ("1", "true", "yes", "on")
        except Exception as e:
            logger.debug("read_self_heal_enabled: %s", e)
            return True

    def write_plugin_health(self, account_id: str, status: str, extra: Optional[Dict[str, Any]] = None) -> None:
        body = {
            "status": status,
            "account_id": account_id,
            "updated_at": time.time(),
            "env": self._env,
        }
        if extra:
            body.update(extra)
        key = IB_GATEWAY_HEALTH_PREFIX + account_id
        self._rds.set(key, json.dumps(body, default=str), ex=30)

    def _write_hash(self, key: str, fields: Dict[str, Any]) -> None:
        mapping = {k: str(v) for k, v in fields.items()}
        try:
            self._rds.hset(key, mapping=mapping)
        except Exception as e:
            err = str(e).lower()
            if "wrongtype" in err or "wrong kind" in err:
                self._rds.delete(key)
                self._rds.hset(key, mapping=mapping)
            else:
                logger.warning("hset %s failed: %s", key, e)
