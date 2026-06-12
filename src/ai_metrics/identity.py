"""Canonical identity handling: user_id is the lowercase email address."""

from __future__ import annotations

import duckdb


def canon_email(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    if s in ("", "nan", "none"):
        return ""
    return s


def ensure_users(con: duckdb.DuckDBPyConnection, user_ids: list[str]) -> None:
    """Insert users seen in usage data but missing from the roster.

    They land in department '(unmapped)' so the gap is visible on the
    dashboard instead of silently dropping their usage from per-department
    rollups.
    """
    user_ids = [u for u in user_ids if u]
    if not user_ids:
        return
    existing = {row[0] for row in con.execute("SELECT user_id FROM dim_user").fetchall()}
    for u in user_ids:
        if u not in existing:
            con.execute(
                "INSERT INTO dim_user (user_id, display_name, department) VALUES (?, ?, ?)",
                [u, u.split("@")[0], "(unmapped)"],
            )
            existing.add(u)
