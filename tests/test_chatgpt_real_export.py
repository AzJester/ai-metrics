"""Tests against the real ChatGPT Enterprise workspace-analytics export
format (period-grain, message totals, no active-day counts)."""

from datetime import date

import pandas as pd

from ai_metrics.ingest import exports
from ai_metrics.ingest.base import upsert_facts

REAL_HEADER = [
    "cadence", "period_start", "period_end", "account_id", "public_id", "name",
    "email", "role", "user_role", "department", "groups", "user_status",
    "created_or_invited_date", "is_active", "first_day_active_in_period",
    "last_day_active_in_period", "messages", "messages_rank", "model_to_messages",
    "gpt_messages", "gpts_messaged", "gpt_to_messages", "tool_messages",
    "tools_messaged", "tool_to_messages", "project_messages", "projects_messaged",
    "project_to_messages", "projects_created", "last_day_active", "credits_used",
]


def _row(email, status, messages):
    r = dict.fromkeys(REAL_HEADER, None)
    r.update(
        cadence="Date Range", period_start="2026-05-12", period_end="2026-06-11",
        email=email, user_status=status, messages=messages,
    )
    return r


def _real_df():
    return pd.DataFrame(
        [
            _row("heavy@astrion.us", "enabled", 1123),
            _row("light@astrion.us", "enabled", 4),
            _row("idle@astrion.us", "enabled", 0),
            _row("invited@astrion.us", "pending", None),
        ]
    )


def test_real_export_parses():
    facts = exports.parse_chatgpt(_real_df())
    msgs = facts[facts["metric"] == "messages"]
    # Pending user with empty messages produces no fact; 0-message user keeps
    # a zero fact (marks the seat, never counts as active).
    assert len(msgs) == 3
    assert msgs["value"].sum() == 1127
    user_facts = facts[facts["user_id"] != ""]
    assert (user_facts["date"] == date(2026, 5, 12)).all()
    # Org-level seat snapshot, dated at the period-end month.
    snap = facts[facts["user_id"] == ""].set_index("metric")["value"]
    assert snap["seats_enabled"] == 3
    assert snap["seats_pending"] == 1
    assert (facts[facts["user_id"] == ""]["date"] == date(2026, 6, 1)).all()


def test_real_export_kpis(con):
    facts = exports.parse_chatgpt(_real_df())
    upsert_facts(con, facts, "chatgpt", "chatgpt_export", "chatgpt_202606.csv")

    mau = con.execute(
        "SELECT mau FROM kpi_adoption_monthly "
        "WHERE tool_id = 'chatgpt' AND month = DATE '2026-05-01'"
    ).fetchone()[0]
    assert mau == 2  # message senders only; idle and pending excluded

    eng = con.execute(
        "SELECT active_users, messages_per_active_user FROM kpi_engagement_monthly "
        "WHERE tool_id = 'chatgpt' AND month = DATE '2026-05-01'"
    ).fetchone()
    assert eng == (2, 563.5)

    # Hours saved falls back to the per-message multiplier (1 / 2.5 min).
    hrs = con.execute(
        "SELECT hours_saved_conservative, hours_saved_expected FROM kpi_hours_saved_monthly "
        "WHERE tool_id = 'chatgpt' AND month = DATE '2026-05-01'"
    ).fetchone()
    assert hrs == (round(1127 / 60, 1), round(1127 * 2.5 / 60, 1))


def test_day_grain_beats_message_fallback(con):
    """When daily 'active' facts exist alongside message totals, only the
    day-grain multiplier counts (no double counting)."""
    rows = pd.DataFrame(
        [
            {"date": date(2026, 5, 4), "user_id": "a@x.com", "metric": "active", "value": 1},
            {"date": date(2026, 5, 4), "user_id": "a@x.com", "metric": "messages", "value": 100},
        ]
    )
    upsert_facts(con, rows, "chatgpt", "chatgpt_export", "daily.csv")
    hrs = con.execute(
        "SELECT hours_saved_conservative, hours_saved_expected FROM kpi_hours_saved_monthly "
        "WHERE tool_id = 'chatgpt' AND month = DATE '2026-05-01'"
    ).fetchone()
    # 1 active day x 10/25 min only; the 100 messages add nothing extra.
    assert hrs == (round(10 / 60, 1), round(25 / 60, 1))
