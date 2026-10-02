"""What each redis-ib ACL user may do, checked by ``ACL DRYRUN`` against the real ACL file (debt TD-21).

DRYRUN only asks the ACL whether a user could run a command; nothing is executed. Skipped where no
``redis-server`` (7+) is on PATH.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import redis

ACL_EXAMPLE = Path(__file__).resolve().parents[1] / "k8s" / "redis-ib" / "acl.conf.example"

pytestmark = pytest.mark.skipif(
    shutil.which("redis-server") is None and not os.environ.get("REDIS_IB_ACL_TEST_PORT"),
    reason="redis-server not on PATH",
)

TICK = "ib:ingester:tick:NVDA|STK|||"
STK_SET = "ib:ingester:control:on_demand_stk"
OPT_SET = "ib:option:control:on_demand_opt"
OPT_TS = "ib:option:control:on_demand_opt_ts"
PROD_CMD = "ib:operator:cmd"


def _render(tmp: Path) -> Path:
    """The same rendering install-redis-ib.sh does: fill passwords, drop comments and blank lines."""
    lines = []
    for line in ACL_EXAMPLE.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        for name in ("GATEWAY_PASS", "TRADE_PROD_PASS", "TRADE_DEV_PASS", "TRADE_STG_PASS", "PLATFORM_PASS"):
            line = line.replace(">" + name, ">test-" + name.lower())
        lines.append(line)
    out = tmp / "acl.conf"
    out.write_text("\n".join(lines) + "\n")
    return out


@pytest.fixture(scope="module")
def admin(tmp_path_factory: pytest.TempPathFactory) -> Iterator[redis.Redis]:
    # REDIS_IB_ACL_TEST_PORT: a server already running with the rendered file (e.g. redis:7-alpine
    # in docker, the image redis-ib runs), instead of the local redis-server.
    if os.environ.get("REDIS_IB_ACL_TEST_PORT"):
        yield redis.Redis(
            port=int(os.environ["REDIS_IB_ACL_TEST_PORT"]),
            username="ib-gateway",
            password="test-gateway_pass",
            decode_responses=True,
        )
        return
    tmp = tmp_path_factory.mktemp("redis-ib-acl")
    acl = _render(tmp)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        ["redis-server", "--port", str(port), "--bind", "127.0.0.1", "--save", "", "--appendonly", "no",
         "--dir", str(tmp), "--aclfile", str(acl)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = redis.Redis(port=port, username="ib-gateway", password="test-gateway_pass", decode_responses=True)
    try:
        for _ in range(50):
            try:
                client.ping()
                break
            except redis.ConnectionError:
                time.sleep(0.1)
        yield client
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _may(admin: redis.Redis, user: str, *command: str) -> bool:
    try:
        return admin.execute_command("ACL", "DRYRUN", user, *command) == "OK"
    except redis.ResponseError:
        return False


ENV_USERS = [("trade-dev", "dev", "stg"), ("trade-stg", "stg", "dev")]


@pytest.mark.parametrize(("user", "own", "other"), ENV_USERS)
def test_env_user_reads_the_bus_and_subscribes(admin: redis.Redis, user: str, own: str, other: str) -> None:
    for command in (
        ("GET", TICK),
        ("HGETALL", "ib:account:snapshot:v1"),
        ("HGETALL", "bifrost:health:ws_ib_operator"),
        ("GET", "ib:operator:result:r1"),
        ("GET", "ib:option:cache:NVDA|OPT|20261016|C|200"),
        ("SMEMBERS", STK_SET),
        ("HGETALL", OPT_TS),
        ("XINFO", "STREAM", PROD_CMD),
        ("SUBSCRIBE", "ib:ingester:channel"),
        ("PSUBSCRIBE", "ib:*"),
        ("PING",),
    ):
        assert _may(admin, user, *command), command


@pytest.mark.parametrize(("user", "own", "other"), ENV_USERS)
def test_env_user_writes_only_its_stream_and_registrations(admin: redis.Redis, user: str, own: str, other: str) -> None:
    assert _may(admin, user, "XADD", f"{PROD_CMD}:{own}", "*", "op", "ping")
    assert _may(admin, user, "SADD", STK_SET, "NVDA")
    assert _may(admin, user, "HSET", OPT_TS, "NVDA|OPT|20261016|C|200", "1")
    assert _may(admin, user, "SADD", OPT_SET, "NVDA|OPT|20261016|C|200")

    for command in (
        ("XADD", PROD_CMD, "*", "op", "ping"),
        ("XADD", f"{PROD_CMD}:{other}", "*", "op", "ping"),
        ("XGROUP", "DESTROY", PROD_CMD, "ib-gateway"),
        ("DEL", f"{PROD_CMD}:{own}"),
        ("SREM", STK_SET, "NVDA"),
        ("HDEL", OPT_TS, "NVDA|OPT|20261016|C|200"),
        ("DEL", TICK),
        ("SET", TICK, "{}"),
        ("PUBLISH", "ib:ingester:channel", "{}"),
        ("HSET", "bifrost:health:daemon_strategy_trading", "ts", "1"),
        ("HSET", "bifrost:health:ws_ib_operator", "ts", "1"),
        ("HSET", "ib:control:gateway_self_heal", "x", "1"),
        ("FLUSHALL",),
        ("CONFIG", "SET", "maxmemory", "1"),
        ("CLIENT", "KILL", "ID", "1"),
        ("ACL", "SETUSER", user, "+@all"),
    ):
        assert not _may(admin, user, *command), command


def test_prod_user_keeps_full_bus_access(admin: redis.Redis) -> None:
    assert _may(admin, "trade-prod", "XADD", PROD_CMD, "*", "op", "ping")
    assert _may(admin, "trade-prod", "DEL", TICK)
    assert _may(admin, "trade-prod", "HSET", "bifrost:health:daemon_strategy_trading", "ts", "1")


def test_gateway_reads_every_operator_stream(admin: redis.Redis) -> None:
    for stream in (PROD_CMD, f"{PROD_CMD}:dev", f"{PROD_CMD}:stg"):
        assert _may(admin, "ib-gateway", "XREADGROUP", "GROUP", "ib-gateway", "c", "STREAMS", stream, ">")
        assert _may(admin, "ib-gateway", "XACK", stream, "ib-gateway", "1-0")
