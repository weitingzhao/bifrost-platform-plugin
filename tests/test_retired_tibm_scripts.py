"""Retired IB socket workloads are not live procedures (TD-125)."""

from __future__ import annotations

from pathlib import Path

_RETIRED = ("ib-market-gateway", "ib-account-agent", "ib-operator")
# Redis consumer-group default written into dev compose config. Not a Kubernetes workload.
_ALLOW = {"scripts/sync-redis-ib-dev-compose-config.sh"}


def test_retired_workload_names_stay_in_scripts_archive() -> None:
    root = Path(__file__).resolve().parents[1]
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "test_retired_tibm_scripts.py":
            continue
        if "archive" in path.parts or path.suffix not in {".sh", ".py", ".md", ".yaml", ".yml"}:
            continue
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        if rel in _ALLOW:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in _RETIRED:
            if name in text:
                hits.append(f"{rel}:{name}")
    assert hits == []
