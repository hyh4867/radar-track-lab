"""YAML configuration loading with dotted overrides."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def with_overrides(cfg: dict[str, Any], **dotted: Any) -> dict[str, Any]:
    """Return a deep copy of ``cfg`` with ``{"radar.pd": 0.8}``-style overrides."""
    out = copy.deepcopy(cfg)
    for key, value in dotted.items():
        node = out
        parts = key.split(".")
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = value
    return out
