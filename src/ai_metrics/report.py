"""Console KPI report and curated-table export (for Power BI)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

CURATED_TABLES = [
    "kpi_adoption_monthly",
    "kpi_engagement_monthly",
    "kpi_retention_monthly",
    "kpi_hours_saved_monthly",
    "kpi_roi_monthly",
    "kpi_survey_summary",
    "v_department_monthly",
    "v_source_freshness",
    "v_multiplier_current",
]


def _df(con: duckdb.DuckDBPyConnection, sql: str, params=None) -> pd.DataFrame:
    return con.execute(sql, params or []).df()


def latest_month(con: duckdb.DuckDBPyConnection) -> str | None:
    row = con.execute("SELECT MAX(date_trunc('month', date))::DATE FROM fact_usage_daily").fetchone()
    return str(row[0]) if row and row[0] else None


def print_report(con: duckdb.DuckDBPyConnection, month: str | None = None) -> None:
    month = month or latest_month(con)
    if month is None:
        print("No usage data ingested yet. Run `ai-metrics ingest` first "
              "(or `ai-metrics sample-data` for a demo).")
        return

    print(f"\n=== AI usage KPIs for month starting {month} ===\n")

    adoption = _df(
        con,
        """
        SELECT display_name AS tool, mau, licensed_seats AS seats,
               activation_rate, seats_inactive, data_quality
        FROM kpi_adoption_monthly WHERE month = ? ORDER BY mau DESC NULLS LAST
        """,
        [month],
    )
    print("-- Adoption --")
    print(adoption.to_string(index=False) if not adoption.empty else "(no data)")

    roi = _df(
        con,
        """
        SELECT display_name AS tool,
               hours_saved_conservative AS hrs_cons, hours_saved_expected AS hrs_exp,
               value_conservative_usd AS value_cons, value_expected_usd AS value_exp,
               monthly_cost_usd AS cost, roi_conservative AS roi_cons,
               roi_expected AS roi_exp, cost_per_active_user_usd AS cost_per_mau
        FROM kpi_roi_monthly WHERE month = ? ORDER BY hours_saved_expected DESC NULLS LAST
        """,
        [month],
    )
    print("\n-- Hours saved & ROI (conservative / expected range; see PLAN.md section 3) --")
    print(roi.to_string(index=False) if not roi.empty else "(no data)")

    survey = _df(con, "SELECT * FROM kpi_survey_summary ORDER BY month")
    print("\n-- Survey calibration --")
    print(survey.to_string(index=False) if not survey.empty else "(no survey responses yet)")

    fresh = _df(con, "SELECT * FROM v_source_freshness ORDER BY source")
    print("\n-- Source freshness --")
    print(fresh.to_string(index=False) if not fresh.empty else "(nothing ingested)")
    print()


def export_curated(con: duckdb.DuckDBPyConnection, out_dir: Path) -> list[Path]:
    """Write each KPI view to CSV for Power BI (or any BI tool) to pick up."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for table in CURATED_TABLES:
        path = out_dir / f"{table}.csv"
        _df(con, f"SELECT * FROM {table}").to_csv(path, index=False)
        written.append(path)
    return written
