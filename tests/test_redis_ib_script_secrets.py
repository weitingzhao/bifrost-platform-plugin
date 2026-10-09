"""TD-278: redis-ib write-user passwords after W-33 step 3.

LANE-W33D moved REDIS_IB_GATEWAY_PASS and REDIS_IB_TRADE_PROD_PASS out of the
plugin .env into the Owner's env file. Every script that reads them must load
that file after the plugin .env, and no script may write a password into the
tracked bifrost-trade-infra config.dev.yaml (the repo is public).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
MOVED = re.compile(r"\$\{?REDIS_IB_(?:GATEWAY|TRADE_PROD)_PASS\b")
PLUGIN_ENV_SOURCE = re.compile(r'^\s*source "\$(?:ENV_FILE|PLUGIN_ENV)"', re.M)
OWNER_ENV_SOURCE = re.compile(r'^\s*source "\$OWNER_ENV"', re.M)


def _live_scripts() -> list[Path]:
    return sorted(p for p in SCRIPTS.glob("*.sh") if p.is_file())


def test_scripts_that_read_moved_keys_load_the_owner_env() -> None:
    readers = [p for p in _live_scripts() if MOVED.search(p.read_text(encoding="utf-8"))]
    assert readers, "expected at least the verify scripts to read the moved keys"
    missing = []
    for path in readers:
        text = path.read_text(encoding="utf-8")
        plugin = PLUGIN_ENV_SOURCE.search(text)
        owner = OWNER_ENV_SOURCE.search(text)
        if "BIFROST_OWNER_ENV" not in text or not owner or (plugin and owner.start() < plugin.start()):
            missing.append(path.name)
    assert not missing, f"read REDIS_IB_GATEWAY_PASS / REDIS_IB_TRADE_PROD_PASS without the Owner env: {missing}"


def test_dev_compose_sync_never_writes_a_password(tmp_path: Path) -> None:
    env_file = tmp_path / "plugin.env"
    env_file.write_text("REDIS_IB_TRADE_DEV_PASS=dev-not-written\n", encoding="utf-8")
    cfg = tmp_path / "config.dev.yaml"
    cfg.write_text("redis:\n  host: localhost\n  port: 6379\n", encoding="utf-8")
    env = dict(os.environ)
    env.update(
        {
            "ENV_FILE": str(env_file),
            "TRADE_INFRA_CONFIG": str(cfg),
            "BIFROST_OWNER_ENV": str(tmp_path / "no-owner.env"),
            "REDIS_IB_TRADE_PROD_PASS": "prod-not-written",
        }
    )
    result = subprocess.run(
        ["bash", str(SCRIPTS / "sync-redis-ib-dev-compose-config.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = cfg.read_text(encoding="utf-8")
    assert "redis_ib:" in text
    assert "username: trade-prod" in text
    assert 'password: ""' in text
    for secret in ("prod-not-written", "dev-not-written"):
        assert secret not in text
        assert secret not in result.stdout + result.stderr
