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
    IB_INGESTER_CHANNEL,
    IB_INGESTER_HEALTH_KEY,
    IB_INGESTER_SUBSCRIPTIONS_KEY,
    IB_INGESTER_TICK_PREFIX,
    IB_INGESTER_TICK_TTL_SEC,
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

    def set_subscriptions(self, keys: Set[str]) -> None:
        pipe = self._rds.pipeline()
        pipe.delete(IB_INGESTER_SUBSCRIPTIONS_KEY)
        if keys:
            pipe.sadd(IB_INGESTER_SUBSCRIPTIONS_KEY, *sorted(keys))
        pipe.execute()

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
