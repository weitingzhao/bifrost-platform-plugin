"""Gateway health hashes carry updated_at so a stopped writer cannot freeze 'live' (TD-104)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from bifrost_plugin.ib_gateway.writer import GatewayRedisWriter


class _Redis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hashes[key] = dict(mapping)

    def set(self, *args: object, **kwargs: object) -> None:
        return None

    def publish(self, *args: object, **kwargs: object) -> None:
        return None


def test_three_health_hashes_stamp_updated_at() -> None:
    rds = _Redis()
    writer = GatewayRedisWriter(rds, env="test")
    before = time.time()
    writer.write_ingestor_health({"connected": "1"})
    writer.write_account_health({"host_connected": "1"})
    writer.write_operator_health({"host_connected": "1"})
    manifest = json.loads(
        (Path(__file__).resolve().parent / "contracts" / "redis_ib_keys.json").read_text(encoding="utf-8")
    )
    fields = manifest["health_hash_fields"]
    keys = manifest["keys"]
    for name, required in fields.items():
        written = rds.hashes[keys[name]]
        for field in required:
            assert field in written, name
        assert float(written["updated_at"]) >= before
        assert "sha" not in written


def test_account_snapshot_does_not_xadd_the_retired_stream() -> None:
    """TD-236: ib:account:stream:v1 has no consumer."""
    src = Path(__file__).resolve().parents[1] / "src" / "bifrost_plugin" / "ib_gateway" / "writer.py"
    text = src.read_text(encoding="utf-8")
    assert "xadd" not in text
    assert "ib:account:stream" not in text
