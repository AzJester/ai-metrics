"""HR roster ingest: refreshes dim_user (department, role, burdened rate).

Expected columns: email, [name], [department], [role_family],
[burdened_rate], [active]. Refresh monthly so per-department KPIs track
hires and leavers.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from ..identity import canon_email
from .base import normalize_headers, numeric, pick_col, require_col


def ingest(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, file_or_run: str) -> int:
    df = normalize_headers(df)
    email_col = require_col(df, ["email", "user_email", "email_address", "mail"], "email")
    name_col = pick_col(df, ["name", "display_name", "full_name"])
    dept_col = pick_col(df, ["department", "dept", "org_unit"])
    role_col = pick_col(df, ["role_family", "role", "job_family", "title"])
    rate_col = pick_col(df, ["burdened_rate", "hourly_rate", "rate"])
    active_col = pick_col(df, ["active", "is_active", "employed"])

    rates = numeric(df[rate_col]) if rate_col else None
    count = 0
    for i in range(len(df)):
        user_id = canon_email(df[email_col].iloc[i])
        if not user_id:
            continue
        rate = None
        if rates is not None and pd.notna(rates.iloc[i]):
            rate = float(rates.iloc[i])
        active = True
        if active_col is not None:
            raw = str(df[active_col].iloc[i]).strip().lower()
            active = raw not in ("0", "false", "no", "n", "inactive", "terminated")
        con.execute(
            """
            INSERT OR REPLACE INTO dim_user
                (user_id, display_name, department, role_family, burdened_rate, active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                user_id,
                str(df[name_col].iloc[i]) if name_col else user_id.split("@")[0],
                str(df[dept_col].iloc[i]) if dept_col else "(unmapped)",
                str(df[role_col].iloc[i]) if role_col else None,
                rate,
                active,
            ],
        )
        count += 1
    con.execute(
        "INSERT INTO ingest_log (source, file_or_run, rows_loaded, min_date, max_date) "
        "VALUES ('roster', ?, ?, NULL, NULL)",
        [file_or_run, count],
    )
    return count
