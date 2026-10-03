"""The redis-ib names the gateway writes match the list Trade core reads them from (debt TD-31).

Trade core (api / worker) reads the gateway's ticks, option cache, account snapshot and health
hashes, and sends Operator RPCs on its command streams. The plugin never imports Trade code, so
both repos test against one list:

    bifrost-trade-core       tests/contracts/redis_ib_keys.json   (canonical)
    bifrost-platform-plugin  tests/contracts/redis_ib_keys.json   (this copy, byte-identical)

Here: redis_keys.py against this copy, every redis-ib literal in the plugin against it, and this
copy against core's. The last one needs bifrost-trade-core checked out next to this repo (the
workspace layout) or at BIFROST_TRADE_CORE_ROOT; without it the test FAILS rather than skips, so
a run that cannot see core's list says so. BIFROST_SKIP_CORE_CONTRACT_SYNC=1 opts out explicitly.

Strings are compared only: nothing here talks to Redis.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

import bifrost_plugin
from bifrost_plugin.ib_gateway import config, redis_keys
from bifrost_plugin.ib_gateway.settings import GatewaySettings, load_settings

MANIFEST = Path(__file__).resolve().parent / "contracts" / "redis_ib_keys.json"
CORE_COPY = Path("tests") / "contracts" / "redis_ib_keys.json"


def _load_manifest(path: Path) -> dict[str, object]:
    keys = json.loads(path.read_text(encoding="utf-8"))["keys"]
    return {k: tuple(v) if isinstance(v, list) else v for k, v in keys.items()}


KEYS = _load_manifest(MANIFEST)


def _module_constants() -> dict[str, object]:
    return {
        name: value
        for name, value in vars(redis_keys).items()
        if name.isupper() and not name.startswith("_") and isinstance(value, (str, int, tuple))
    }


def test_redis_keys_module_matches_manifest() -> None:
    constants = _module_constants()
    assert sorted(constants) == sorted(KEYS), (
        "redis_keys.py and tests/contracts/redis_ib_keys.json name different constants; "
        "a new or removed name goes into the manifest here and in bifrost-trade-core"
    )
    for name, value in KEYS.items():
        assert constants[name] == value, name


def _core_root() -> Path:
    env = os.environ.get("BIFROST_TRADE_CORE_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "bifrost-trade-core"


def test_manifest_is_core_copy() -> None:
    core_manifest = _core_root() / CORE_COPY
    if not core_manifest.is_file():
        if os.environ.get("BIFROST_SKIP_CORE_CONTRACT_SYNC") == "1":
            pytest.skip("BIFROST_SKIP_CORE_CONTRACT_SYNC=1: core's copy not compared")
        pytest.fail(
            f"core's redis-ib manifest not found at {core_manifest}. Check out bifrost-trade-core "
            "next to this repo or set BIFROST_TRADE_CORE_ROOT (BIFROST_SKIP_CORE_CONTRACT_SYNC=1 "
            "skips this check on purpose)."
        )
    assert MANIFEST.read_bytes() == core_manifest.read_bytes(), (
        f"{MANIFEST} differs from {core_manifest}: the gateway and Trade core disagree on a "
        "redis-ib name. Change both repos and both copies together."
    )


# --- ratchet: every redis-ib literal in the plugin is in the manifest ------------------------

# Literals that are neither a manifest value nor a template over one, with why.
PLUGIN_ONLY_LITERALS = {
    "ib:",  # config.REDIS_IB_KEY_PREFIX: a namespace label, not a key
    # config.py templates that nothing in the plugin or Trade core reads or writes:
    "ib:account:{account_id}:positions",
    "ib:account:{account_id}:summary",
    "ib:events:{account_id}",
    "ib:control:{account_id}",
}


def _plugin_redis_literals() -> set[str]:
    root = Path(bifrost_plugin.__file__).resolve().parent
    out: set[str] = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.startswith(("ib:", "bifrost:health:", "|STK"))
            ):
                out.add(node.value)
    return out


def _manifest_strings() -> set[str]:
    out: set[str] = set()
    for value in KEYS.values():
        if isinstance(value, str):
            out.add(value)
        elif isinstance(value, tuple):
            out.update(value)
    return out


def test_every_redis_literal_in_the_plugin_is_in_the_manifest() -> None:
    known = _manifest_strings()
    unknown = set()
    for literal in _plugin_redis_literals() - known - PLUGIN_ONLY_LITERALS:
        # "ib:health:{account_id}" is fine when "ib:health:" is a manifest prefix.
        if "{" in literal and literal.split("{", 1)[0] in known:
            continue
        unknown.add(literal)
    assert not unknown, f"redis-ib names the plugin uses that the manifest does not list: {unknown}"


def test_plugin_only_literals_are_still_there() -> None:
    """An allowlist entry that no longer occurs in the code is removed, not kept."""
    assert PLUGIN_ONLY_LITERALS <= _plugin_redis_literals()


# --- the same names spelled a second time inside the plugin ----------------------------------


def test_config_templates_build_manifest_keys() -> None:
    ck = redis_keys.stk_contract_key("XYZ")
    assert config.REDIS_TICK_PATTERN.format(contract_key=ck) == KEYS["IB_INGESTER_TICK_PREFIX"] + ck
    assert config.REDIS_OPERATOR_CMD == KEYS["IB_OPERATOR_CMD_STREAM"]
    assert config.REDIS_OPERATOR_RESULT.format(request_id="") == KEYS["IB_OPERATOR_RESULT_PREFIX"]
    assert config.REDIS_HEALTH.format(account_id="") == KEYS["IB_GATEWAY_HEALTH_PREFIX"]
    assert ck.endswith(KEYS["STK_CONTRACT_KEY_SUFFIX"])


def test_settings_max_age_defaults_match_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """settings.py repeats the on-demand heartbeat max ages; Trade's pollers are tuned to them."""
    monkeypatch.delenv("IB_GATEWAY_ON_DEMAND_OPT_MAX_AGE_SEC", raising=False)
    for settings in (GatewaySettings(), load_settings(str(tmp_path / "absent.yaml"))):
        assert settings.on_demand_max_age_sec == KEYS["ON_DEMAND_STK_DEFAULT_MAX_AGE_SEC"]
        assert settings.on_demand_opt_max_age_sec == KEYS["ON_DEMAND_OPT_DEFAULT_MAX_AGE_SEC"]
