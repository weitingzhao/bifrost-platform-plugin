"""TD-122 + TD-104: the three health hashes carry the image git SHA and a liveness timestamp."""

from unittest.mock import MagicMock

from bifrost_plugin.ib_gateway.redis_keys import (
    IB_ACCOUNT_AGENT_HEALTH_KEY,
    IB_INGESTER_HEALTH_KEY,
    IB_OPERATOR_HEALTH_KEY,
)
from bifrost_plugin.ib_gateway.writer import GatewayRedisWriter


def test_health_hashes_carry_git_sha_and_updated_at(monkeypatch) -> None:
    sha = "a" * 40
    monkeypatch.setenv("IB_GATEWAY_GIT_SHA", sha)
    rds = MagicMock()
    writer = GatewayRedisWriter(rds, env="platform")
    writer.write_ingestor_health({"connected": True})
    writer.write_account_health({"host_connected": True})
    writer.write_operator_health({"mode": "live"})

    seen = {call.args[0]: call.kwargs["mapping"] for call in rds.hset.call_args_list}
    assert set(seen) == {
        IB_INGESTER_HEALTH_KEY,
        IB_ACCOUNT_AGENT_HEALTH_KEY,
        IB_OPERATOR_HEALTH_KEY,
    }
    for mapping in seen.values():
        assert mapping["git_sha"] == sha
        assert float(mapping["updated_at"]) > 0


def test_git_sha_field_is_present_when_the_image_did_not_set_it(monkeypatch) -> None:
    monkeypatch.delenv("IB_GATEWAY_GIT_SHA", raising=False)
    rds = MagicMock()
    GatewayRedisWriter(rds, env="platform").write_operator_health({"mode": "live"})
    mapping = rds.hset.call_args.kwargs["mapping"]
    assert mapping["git_sha"] == ""
