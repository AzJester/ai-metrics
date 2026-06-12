"""Load tool registry and task-time multipliers from config/*.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

VALID_DATA_QUALITY = {"api", "export", "vendor", "survey"}


def config_dir() -> Path:
    return Path(os.environ.get("AI_METRICS_CONFIG_DIR", "config"))


def load_tools(path: Path | None = None) -> dict:
    path = path or config_dir() / "tools.yaml"
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if "tools" not in cfg or not cfg["tools"]:
        raise ValueError(f"{path}: missing 'tools' section")
    for tool_id, t in cfg["tools"].items():
        dq = t.get("data_quality")
        if dq not in VALID_DATA_QUALITY:
            raise ValueError(
                f"{path}: tool '{tool_id}' has data_quality={dq!r}, "
                f"expected one of {sorted(VALID_DATA_QUALITY)}"
            )
    cfg.setdefault("defaults", {})
    cfg["defaults"].setdefault("burdened_rate", 85)
    return cfg


def load_multipliers(path: Path | None = None) -> dict:
    path = path or config_dir() / "multipliers.yaml"
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if not cfg.get("version"):
        raise ValueError(f"{path}: missing 'version'")
    rows = []
    for entry in cfg.get("multipliers", []):
        for metric in entry["metrics"]:
            rows.append(
                {
                    "tool_id": entry["tool"],
                    "metric": metric,
                    "unit": entry.get("unit", ""),
                    "minutes_saved_conservative": float(entry["conservative"]),
                    "minutes_saved_expected": float(entry["expected"]),
                    "basis": entry.get("basis", ""),
                    "version": str(cfg["version"]),
                }
            )
    if not rows:
        raise ValueError(f"{path}: no multipliers defined")
    return {"version": str(cfg["version"]), "rows": rows}
