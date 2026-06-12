"""KPI math checks against hand-computed fixtures."""

from datetime import date

import pandas as pd

from ai_metrics.ingest.base import upsert_facts


def _load(con, rows, tool, source):
    upsert_facts(con, pd.DataFrame(rows), tool, source, "fixture")


def test_adoption_and_activation(con):
    con.execute("UPDATE dim_tool SET licensed_seats = 10 WHERE tool_id = 'chatgpt'")
    _load(
        con,
        [
            {"date": date(2026, 5, 4), "user_id": "a@x.com", "metric": "active", "value": 1},
            {"date": date(2026, 5, 5), "user_id": "a@x.com", "metric": "active", "value": 1},
            {"date": date(2026, 5, 4), "user_id": "b@x.com", "metric": "active", "value": 1},
        ],
        "chatgpt",
        "chatgpt_export",
    )
    row = con.execute(
        "SELECT mau, activation_rate, seats_inactive FROM kpi_adoption_monthly "
        "WHERE tool_id = 'chatgpt' AND month = DATE '2026-05-01'"
    ).fetchone()
    assert row == (2, 0.2, 8)


def test_org_level_fallback(con):
    _load(
        con,
        [
            {"date": date(2026, 5, 4), "user_id": "", "metric": "active_users", "value": 40},
            {"date": date(2026, 5, 11), "user_id": "", "metric": "active_users", "value": 55},
        ],
        "rovo",
        "rovo_export",
    )
    mau = con.execute(
        "SELECT mau FROM kpi_adoption_monthly WHERE tool_id = 'rovo' "
        "AND month = DATE '2026-05-01'"
    ).fetchone()[0]
    assert mau == 55  # peak reported value


def test_hours_saved_uses_multipliers_and_dedupes_sources(con):
    # Known multiplier for the test, newer than any config version.
    con.execute(
        "INSERT OR REPLACE INTO multiplier VALUES "
        "('chatgpt', 'active', 'active day', 30, 60, 'test', '9999-01')"
    )
    rows = [
        {"date": date(2026, 5, 4), "user_id": "a@x.com", "metric": "active", "value": 1},
        {"date": date(2026, 5, 5), "user_id": "a@x.com", "metric": "active", "value": 1},
    ]
    _load(con, rows, "chatgpt", "chatgpt_export")
    # Same days arriving from a second source must not double the hours.
    _load(con, rows, "chatgpt", "openai_api")
    row = con.execute(
        "SELECT hours_saved_conservative, hours_saved_expected FROM kpi_hours_saved_monthly "
        "WHERE tool_id = 'chatgpt' AND month = DATE '2026-05-01'"
    ).fetchone()
    assert row == (1.0, 2.0)  # 2 active days x 30/60 min


def test_roi_math(con):
    con.execute(
        "INSERT OR REPLACE INTO multiplier VALUES "
        "('pwin', 'drafts', 'draft', 60, 120, 'test', '9999-01')"
    )
    con.execute(
        "UPDATE dim_tool SET licensed_seats = 10, monthly_cost_per_seat = 100, "
        "monthly_flat_cost = 0 WHERE tool_id = 'pwin'"
    )
    con.execute(
        "INSERT OR REPLACE INTO config_kv VALUES ('default_burdened_rate', '100')"
    )
    _load(
        con,
        [{"date": date(2026, 5, 4), "user_id": "a@x.com", "metric": "drafts", "value": 20}],
        "pwin",
        "pwin_export",
    )
    row = con.execute(
        "SELECT hours_saved_conservative, value_conservative_usd, monthly_cost_usd, "
        "roi_conservative FROM kpi_roi_monthly "
        "WHERE tool_id = 'pwin' AND month = DATE '2026-05-01'"
    ).fetchone()
    # 20 drafts x 60 min = 20 hrs; value 20x$100=$2000; cost $1000; ROI (2000-1000)/1000 = 1.0
    assert row == (20.0, 2000.0, 1000.0, 1.0)


def test_retention(con):
    _load(
        con,
        [
            {"date": date(2026, 4, 6), "user_id": "a@x.com", "metric": "active", "value": 1},
            {"date": date(2026, 4, 6), "user_id": "b@x.com", "metric": "active", "value": 1},
            {"date": date(2026, 5, 4), "user_id": "a@x.com", "metric": "active", "value": 1},
        ],
        "chatgpt",
        "chatgpt_export",
    )
    row = con.execute(
        "SELECT active_users, retained_next_month, retention_rate FROM kpi_retention_monthly "
        "WHERE tool_id = 'chatgpt' AND month = DATE '2026-04-01'"
    ).fetchone()
    assert row == (2, 1, 0.5)
