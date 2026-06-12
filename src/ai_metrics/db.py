"""DuckDB warehouse: connection, schema, config seeding, KPI views."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

import duckdb

from . import config as cfg

DEFAULT_DB_PATH = "data/warehouse.duckdb"


def db_path() -> Path:
    return Path(os.environ.get("AI_METRICS_DB", DEFAULT_DB_PATH))


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def _read_sql(name: str) -> str:
    return resources.files("ai_metrics").joinpath(name).read_text()


def init_db(con: duckdb.DuckDBPyConnection) -> None:
    """Create tables, seed config (tools, rate, multipliers), create views.

    Idempotent: safe to run before every command so config edits are always
    reflected in the warehouse.
    """
    con.execute(_read_sql("schema.sql"))

    tools = cfg.load_tools()
    for tool_id, t in tools["tools"].items():
        con.execute(
            """
            INSERT OR REPLACE INTO dim_tool
                (tool_id, display_name, vendor, monthly_cost_per_seat,
                 monthly_flat_cost, licensed_seats, data_quality)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                tool_id,
                t.get("display_name", tool_id),
                t.get("vendor", ""),
                float(t.get("monthly_cost_per_seat", 0)),
                float(t.get("monthly_flat_cost", 0)),
                int(t.get("licensed_seats", 0)),
                t["data_quality"],
            ],
        )
    con.execute(
        "INSERT OR REPLACE INTO config_kv (key, value) VALUES ('default_burdened_rate', ?)",
        [str(tools["defaults"]["burdened_rate"])],
    )

    mult = cfg.load_multipliers()
    for r in mult["rows"]:
        con.execute(
            """
            INSERT OR REPLACE INTO multiplier
                (tool_id, metric, unit, minutes_saved_conservative,
                 minutes_saved_expected, basis, version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                r["tool_id"],
                r["metric"],
                r["unit"],
                r["minutes_saved_conservative"],
                r["minutes_saved_expected"],
                r["basis"],
                r["version"],
            ],
        )

    con.execute(_read_sql("views.sql"))


def connect_and_init() -> duckdb.DuckDBPyConnection:
    con = connect()
    init_db(con)
    return con
