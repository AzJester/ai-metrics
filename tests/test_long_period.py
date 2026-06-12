"""Long-period (e.g. 12-month) export spreading: estimated monthly
distribution from each user's observed activity window."""

from datetime import date

import pandas as pd
import pytest

from ai_metrics.ingest import exports
from ai_metrics.ingest.base import upsert_facts
from ai_metrics.ingest.peruser_chat import _month_spans


def _row(email, messages, first, last, created="2025-07-01"):
    return {
        "cadence": "Date Range", "period_start": "2025-07-01", "period_end": "2026-06-11",
        "email": email, "user_status": "enabled", "messages": messages,
        "first_day_active_in_period": first, "last_day_active_in_period": last,
        "created_or_invited_date": created,
    }


def test_month_spans():
    spans = _month_spans(date(2026, 1, 15), date(2026, 3, 10))
    assert spans == [(date(2026, 1, 1), 17), (date(2026, 2, 1), 28), (date(2026, 3, 1), 10)]


def test_spread_respects_activity_window():
    df = pd.DataFrame([_row("a@x.com", 550, "2026-04-01", "2026-05-30")])
    facts = exports.parse_chatgpt(df)
    assert set(facts["date"]) == {date(2026, 4, 1), date(2026, 5, 1)}
    # 30 days in April + 30 active days in May (Apr 1 - May 30) = 60 days.
    by_month = facts.set_index("date")["value"]
    assert by_month[date(2026, 4, 1)] == pytest.approx(550 * 30 / 60)
    assert by_month[date(2026, 5, 1)] == pytest.approx(550 * 30 / 60)
    assert facts["value"].sum() == pytest.approx(550)  # total conserved


def test_spread_starts_at_invite_when_no_earlier_activity():
    df = pd.DataFrame([_row("b@x.com", 100, None, None, created="2026-05-01")])
    facts = exports.parse_chatgpt(df)
    assert min(facts["date"]) == date(2026, 5, 1)
    assert facts["value"].sum() == pytest.approx(100)


def test_inconsistent_window_falls_back_to_full_period():
    df = pd.DataFrame([_row("c@x.com", 120, "2026-06-30", "2026-01-01")])
    facts = exports.parse_chatgpt(df)
    assert min(facts["date"]) == date(2025, 7, 1)
    assert facts["value"].sum() == pytest.approx(120)


def test_zero_or_missing_messages_emit_nothing():
    df = pd.DataFrame(
        [_row("idle@x.com", 0, None, None), _row("pending@x.com", None, None, None)]
    )
    assert exports.parse_chatgpt(df).empty


def test_real_monthly_export_replaces_estimate(con):
    yearly = pd.DataFrame([_row("a@x.com", 1200, "2026-01-01", "2026-06-11")])
    upsert_facts(con, exports.parse_chatgpt(yearly), "chatgpt", "chatgpt_export", "year.csv")
    est_may = con.execute(
        "SELECT value FROM fact_usage_daily WHERE user_id='a@x.com' "
        "AND date = DATE '2026-05-01' AND metric='messages'"
    ).fetchone()[0]
    assert est_may > 0

    # A real May export (short period, same month-start key) overwrites it.
    monthly = pd.DataFrame(
        {"email": ["a@x.com"], "period_start": ["2026-05-01"],
         "period_end": ["2026-05-31"], "messages": [333]}
    )
    upsert_facts(con, exports.parse_chatgpt(monthly), "chatgpt", "chatgpt_export", "may.csv")
    real_may = con.execute(
        "SELECT value FROM fact_usage_daily WHERE user_id='a@x.com' "
        "AND date = DATE '2026-05-01' AND metric='messages'"
    ).fetchone()[0]
    assert real_may == 333
