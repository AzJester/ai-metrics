"""Claude Code Analytics API connector (Anthropic Admin API).

Requires ANTHROPIC_ADMIN_KEY (an admin key, sk-ant-admin...). Pulls per-user
daily activity: sessions, lines added, commits. Reference:
https://platform.claude.com/docs/en/manage-claude/claude-code-analytics-api
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import httpx
import pandas as pd

from ..base import make_facts

API_VERSION = "2023-06-01"


def _email_of(record: dict) -> str:
    actor = record.get("actor") or {}
    return (
        record.get("actor_email")
        or actor.get("email_address")
        or actor.get("email")
        or ""
    )


def fetch(days: int = 30) -> pd.DataFrame | None:
    key = os.environ.get("ANTHROPIC_ADMIN_KEY")
    if not key:
        return None
    base = os.environ.get("ANTHROPIC_API_BASE", "https://api.anthropic.com")
    headers = {"x-api-key": key, "anthropic-version": API_VERSION}

    rows = []
    # The endpoint returns one day per request page-set; iterate the window.
    day = date.today() - timedelta(days=days)
    with httpx.Client(timeout=30) as client:
        while day < date.today():
            page = None
            while True:
                params = {"starting_at": day.isoformat(), "limit": 500}
                if page:
                    params["page"] = page
                resp = client.get(
                    f"{base}/v1/organizations/usage_report/claude_code",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                payload = resp.json()
                for rec in payload.get("data", []):
                    email = _email_of(rec)
                    rec_date = date.fromisoformat(str(rec.get("date", day.isoformat()))[:10])
                    core = rec.get("core_metrics") or {}
                    rows.append({"date": rec_date, "user_id": email,
                                 "metric": "active", "value": 1.0})
                    if core.get("num_sessions") is not None:
                        rows.append({"date": rec_date, "user_id": email,
                                     "metric": "sessions", "value": float(core["num_sessions"])})
                    loc = core.get("lines_of_code") or {}
                    if loc.get("added") is not None:
                        rows.append({"date": rec_date, "user_id": email,
                                     "metric": "lines_added", "value": float(loc["added"])})
                    if core.get("commits_by_claude_code") is not None:
                        rows.append({"date": rec_date, "user_id": email, "metric": "commits",
                                     "value": float(core["commits_by_claude_code"])})
                if payload.get("has_more") and payload.get("next_page"):
                    page = payload["next_page"]
                else:
                    break
            day += timedelta(days=1)
    return make_facts(rows)
