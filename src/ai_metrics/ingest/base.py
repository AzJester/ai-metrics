"""Shared ingest helpers: header normalization, column aliases, fact upsert."""

from __future__ import annotations

import re
from datetime import date

import duckdb
import pandas as pd

from ..identity import canon_email, ensure_users

FACT_COLUMNS = ["date", "user_id", "metric", "value"]


class IngestError(Exception):
    pass


def normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase headers and collapse punctuation/whitespace to underscores,
    so 'Period Start', 'period-start' and 'period_start' all match."""
    df = df.copy()
    df.columns = [re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_") for c in df.columns]
    return df


def pick_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def require_col(df: pd.DataFrame, aliases: list[str], what: str) -> str:
    col = pick_col(df, aliases)
    if col is None:
        raise IngestError(
            f"Could not find a {what} column. Looked for any of {aliases}, "
            f"found columns {list(df.columns)}. Rename the export's header or "
            f"add an alias in the ingester."
        )
    return col


def to_dates(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    return parsed.dt.date


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def upsert_facts(
    con: duckdb.DuckDBPyConnection,
    facts: pd.DataFrame,
    tool_id: str,
    source: str,
    file_or_run: str,
) -> int:
    """Idempotent load: same (date, tool, user, metric, source) replaces.

    `source` is the connector family (e.g. 'chatgpt_export'), not the file
    name, so re-ingesting a fresh export that overlaps an old one replaces
    rows instead of double counting.
    """
    if facts is None or facts.empty:
        return 0
    df = facts.copy()
    df["tool_id"] = tool_id
    df["user_id"] = df["user_id"].map(canon_email) if "user_id" in df else ""
    df["source"] = source
    df["value"] = numeric(df["value"])
    df = df.dropna(subset=["date", "metric", "value"])
    if df.empty:
        return 0
    df = df.drop_duplicates(subset=["date", "tool_id", "user_id", "metric", "source"], keep="last")

    ensure_users(con, sorted({u for u in df["user_id"].unique() if u}))

    con.register("_facts_df", df)
    con.execute(
        """
        INSERT OR REPLACE INTO fact_usage_daily (date, tool_id, user_id, metric, value, source)
        SELECT CAST(date AS DATE), tool_id, user_id, metric, CAST(value AS DOUBLE), source
        FROM _facts_df
        """
    )
    con.unregister("_facts_df")

    min_d, max_d = min(df["date"]), max(df["date"])
    con.execute(
        "INSERT INTO ingest_log (source, file_or_run, rows_loaded, min_date, max_date) "
        "VALUES (?, ?, ?, ?, ?)",
        [source, file_or_run, len(df), min_d, max_d],
    )
    return len(df)


def make_facts(rows: list[dict]) -> pd.DataFrame:
    """rows: dicts with date (datetime.date), user_id, metric, value."""
    if not rows:
        return pd.DataFrame(columns=FACT_COLUMNS)
    df = pd.DataFrame(rows)
    missing = set(FACT_COLUMNS) - set(df.columns)
    if missing:
        raise IngestError(f"fact rows missing columns: {missing}")
    return df[FACT_COLUMNS]


def valid_date(d) -> bool:
    return isinstance(d, date) and not pd.isna(d)
