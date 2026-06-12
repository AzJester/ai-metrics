from datetime import date

import pandas as pd
import pytest

from ai_metrics.ingest import exports, route
from ai_metrics.ingest.base import IngestError, upsert_facts


def test_route_prefixes():
    assert route("chatgpt_2026-05.csv") == ("fact", "chatgpt", exports.parse_chatgpt)
    assert route("claude_code_may.csv")[1] == "claude_code"
    assert route("claude_may.csv")[1] == "claude"
    assert route("ROSTER_June.csv") == ("roster",)
    assert route("survey_q2.csv") == ("survey",)
    assert route("mystery.csv") is None


def test_chatgpt_daily_parse():
    df = pd.DataFrame(
        {
            "Email": ["A@Example.com", "b@example.com", "b@example.com"],
            "Date": ["2026-05-04", "2026-05-04", "2026-05-05"],
            "Messages": [12, 0, 5],
        }
    )
    facts = exports.parse_chatgpt(df)
    active = facts[facts["metric"] == "active"]
    # b@ sent 0 messages on 05-04: present in the export but not active.
    assert len(active) == 2
    msgs = facts[facts["metric"] == "messages"]
    assert msgs["value"].sum() == 17


def test_claude_period_parse():
    df = pd.DataFrame(
        {
            "email": ["a@example.com"],
            "period_start": ["2026-05-01"],
            "active_days": [10],
            "messages": [60],
        }
    )
    facts = exports.parse_claude(df)
    assert facts[facts["metric"] == "active_days"]["value"].iloc[0] == 10
    assert facts[facts["metric"] == "messages"]["value"].iloc[0] == 60


def test_missing_column_message():
    df = pd.DataFrame({"who": ["a@example.com"], "date": ["2026-05-01"]})
    with pytest.raises(IngestError, match="user email"):
        exports.parse_chatgpt(df)


def test_rovo_prefers_all_row():
    df = pd.DataFrame(
        {
            "date": ["2026-05-04"] * 3,
            "app": ["Jira", "Confluence", "All"],
            "active_users": [30, 20, 42],
            "actions": [100, 50, 160],
        }
    )
    facts = exports.parse_rovo(df)
    au = facts[facts["metric"] == "active_users"]
    assert au["value"].iloc[0] == 42
    assert (au["user_id"] == "").all()
    actions = facts[facts["metric"] == "actions"]
    assert actions["value"].iloc[0] == 310  # summed across apps


def test_rovo_without_all_row_warns():
    df = pd.DataFrame(
        {
            "date": ["2026-05-04"] * 2,
            "app": ["Jira", "Confluence"],
            "active_users": [30, 20],
        }
    )
    with pytest.warns(UserWarning, match="lower bound"):
        facts = exports.parse_rovo(df)
    assert facts[facts["metric"] == "active_users"]["value"].iloc[0] == 30


def test_upsert_idempotent(con):
    facts = pd.DataFrame(
        [
            {"date": date(2026, 5, 4), "user_id": "A@Example.com",
             "metric": "active", "value": 1.0},
            {"date": date(2026, 5, 4), "user_id": "a@example.com",
             "metric": "messages", "value": 9.0},
        ]
    )
    n1 = upsert_facts(con, facts, "chatgpt", "chatgpt_export", "f1.csv")
    n2 = upsert_facts(con, facts, "chatgpt", "chatgpt_export", "f1_again.csv")
    assert n1 == n2 == 2
    total = con.execute("SELECT COUNT(*) FROM fact_usage_daily").fetchone()[0]
    assert total == 2  # replaced, not duplicated
    # email canonicalized and auto-added to dim_user as unmapped
    dept = con.execute(
        "SELECT department FROM dim_user WHERE user_id = 'a@example.com'"
    ).fetchone()[0]
    assert dept == "(unmapped)"
