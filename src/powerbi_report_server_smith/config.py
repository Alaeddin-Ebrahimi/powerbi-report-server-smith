from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_POLICIES_PATH = Path(__file__).resolve().parents[2] / "config" / "policies.yaml"


def load_policies(path: str | None = None) -> dict:
    p = Path(path) if path else DEFAULT_POLICIES_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
