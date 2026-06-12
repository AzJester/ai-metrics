"""Quarterly pulse survey ingest (MS Forms CSV export).

Expected columns (rename Forms' long question headers to these before
dropping the file, or extend the alias lists):
  timestamp, email, tools_used, weekly_time_saved_band, top_task,
  copilot_days_per_week, dependence
"""

from __future__ import annotations

import re
import warnings

import duckdb
import pandas as pd

from ..identity import canon_email
from .base import normalize_headers, numeric, pick_col, require_col, to_dates, valid_date

# Band -> midpoint minutes per week. Keys are normalized (lowercase, single
# spaces, no unit punctuation).
BAND_MINUTES = {
    "0": 0.0,
    "none": 0.0,
    "<30 min": 15.0,
    "less than 30 min": 15.0,
    "30-60 min": 45.0,
    "1-3 hrs": 120.0,
    "1-3 hours": 120.0,
    "3-8 hrs": 330.0,
    "3-8 hours": 330.0,
    "8+ hrs": 600.0,
    "8+ hours": 600.0,
    "more than 8 hrs": 600.0,
}

TOOL_NAME_MAP = {
    "chatgpt": "chatgpt",
    "chatgpt enterprise": "chatgpt",
    "claude": "claude",
    "claude team": "claude",
    "claude code": "claude_code",
    "copilot": "copilot",
    "github copilot": "copilot",
    "rovo": "rovo",
    "icertis": "icertis",
    "pwin": "pwin",
    "pwin.ai": "pwin",
}


def _norm_band(raw) -> str:
    s = str(raw).strip().lower()
    s = s.replace("–", "-").replace(" - ", "-").replace("hrs.", "hrs")
    return re.sub(r"\s+", " ", s)


def _norm_tools(raw) -> str:
    if raw is None or pd.isna(raw):
        return ""
    parts = re.split(r"[;,]", str(raw))
    ids = []
    for p in parts:
        key = p.strip().lower()
        if not key:
            continue
        tool_id = TOOL_NAME_MAP.get(key)
        if tool_id is None:
            warnings.warn(f"Survey tool name {p.strip()!r} not recognized; skipped.", stacklevel=2)
            continue
        if tool_id not in ids:
            ids.append(tool_id)
    return ",".join(ids)


def ingest(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, file_or_run: str) -> int:
    df = normalize_headers(df)
    ts_col = require_col(
        df, ["timestamp", "submitted_at", "completion_time", "start_time", "date"], "timestamp"
    )
    email_col = require_col(df, ["email", "user_email", "respondent_email", "email_address"],
                            "email")
    band_col = require_col(
        df, ["weekly_time_saved_band", "time_saved", "weekly_time_saved"], "time-saved band"
    )
    tools_col = pick_col(df, ["tools_used", "tools", "which_tools"])
    task_col = pick_col(df, ["top_task", "task", "most_helpful_task"])
    cop_col = pick_col(df, ["copilot_days_per_week", "copilot_days"])
    dep_col = pick_col(df, ["dependence", "impact_if_removed"])

    dates = to_dates(df[ts_col])
    cop_days = numeric(df[cop_col]) if cop_col else None
    count = 0
    for i in range(len(df)):
        d = dates.iloc[i]
        user_id = canon_email(df[email_col].iloc[i])
        if not valid_date(d) or not user_id:
            continue
        band_raw = _norm_band(df[band_col].iloc[i])
        mid = BAND_MINUTES.get(band_raw)
        if mid is None:
            warnings.warn(
                f"Survey band {band_raw!r} not recognized (row {i}); stored without midpoint.",
                stacklevel=2,
            )
        con.execute(
            """
            INSERT OR REPLACE INTO fact_survey
                (survey_date, user_id, tools_used, weekly_minutes_saved_band,
                 weekly_minutes_saved_mid, copilot_days_per_week, dependence, top_task)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                d,
                user_id,
                _norm_tools(df[tools_col].iloc[i]) if tools_col else "",
                band_raw,
                mid,
                float(cop_days.iloc[i]) if cop_days is not None and pd.notna(cop_days.iloc[i])
                else None,
                str(df[dep_col].iloc[i]) if dep_col else None,
                str(df[task_col].iloc[i]) if task_col else None,
            ],
        )
        count += 1
    con.execute(
        "INSERT INTO ingest_log (source, file_or_run, rows_loaded, min_date, max_date) "
        "VALUES ('survey', ?, ?, ?, ?)",
        [file_or_run, count, min(dates.dropna(), default=None), max(dates.dropna(), default=None)],
    )
    return count
