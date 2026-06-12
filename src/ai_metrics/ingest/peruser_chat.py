"""Generic parser for per-user chat-assistant exports (ChatGPT, Claude).

Accepts three grains:
- daily rows:   email, date, [messages]            -> 'active' + 'messages'
- period rows:  email, period_start, [active_days], [messages]
                                                   -> 'active_days' + 'messages'
- long periods: when a row's period spans more than ~6 weeks (e.g. a 12-month
  workspace export with one totals row per user), the total is spread across
  the calendar months of the user's observed activity window
  (first/last day active, bounded by invite date). This is an ESTIMATED
  monthly distribution: annual totals are exact, monthly shape is modeled.
  Real month-grain exports ingested later land on the same (date, user,
  metric, source) keys and replace the estimates.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .base import (
    IngestError,
    make_facts,
    normalize_headers,
    numeric,
    pick_col,
    require_col,
    to_dates,
    valid_date,
)

EMAIL_ALIASES = ["email", "user_email", "user", "member_email", "email_address"]
DATE_ALIASES = ["date", "day", "activity_date"]
PERIOD_ALIASES = ["period_start", "start_date", "week_start", "month_start", "period", "month"]
PERIOD_END_ALIASES = ["period_end", "end_date"]
ACTIVE_DAYS_ALIASES = ["active_days", "days_active", "num_active_days"]
FIRST_ACTIVE_ALIASES = ["first_day_active_in_period", "first_day_active", "first_active"]
LAST_ACTIVE_ALIASES = ["last_day_active_in_period", "last_active"]
CREATED_ALIASES = ["created_or_invited_date", "created_date", "invite_date"]

# Periods longer than this are treated as long-range exports to be spread
# across months rather than booked to a single month bucket.
LONG_PERIOD_DAYS = 40


def _month_spans(start: date, end: date) -> list[tuple[date, int]]:
    """Calendar months overlapping [start, end] as (month_start, overlap_days)."""
    spans = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        s, e = max(start, cur), min(end, nxt - timedelta(days=1))
        days = (e - s).days + 1
        if days > 0:
            spans.append((cur, days))
        cur = nxt
    return spans


def _spread_row(email, total, p_start, p_end, first, last, created) -> list[dict]:
    """Distribute a period total across months of the user's activity window."""
    if total is None or pd.isna(total) or total <= 0:
        return []
    w_start = p_start
    for lower in (created, first):
        if valid_date(lower) and lower > w_start:
            w_start = lower
    w_end = p_end
    if valid_date(last) and last < w_end:
        w_end = last
    if w_start > w_end:  # inconsistent metadata: fall back to the full period
        w_start, w_end = p_start, p_end
    spans = _month_spans(w_start, w_end)
    total_days = sum(d for _, d in spans)
    return [
        {"date": m, "user_id": email, "metric": "messages",
         "value": float(total) * d / total_days}
        for m, d in spans
    ]


def parse(df: pd.DataFrame, messages_aliases: list[str]) -> pd.DataFrame:
    df = normalize_headers(df)
    email_col = require_col(df, EMAIL_ALIASES, "user email")
    date_col = pick_col(df, DATE_ALIASES)
    period_col = pick_col(df, PERIOD_ALIASES)
    msg_col = pick_col(df, messages_aliases)

    rows = []
    if date_col:
        dates = to_dates(df[date_col])
        msgs = numeric(df[msg_col]) if msg_col else None
        for i in range(len(df)):
            d = dates.iloc[i]
            if not valid_date(d):
                continue
            email = df[email_col].iloc[i]
            m = float(msgs.iloc[i]) if msgs is not None and pd.notna(msgs.iloc[i]) else None
            # A daily row means the user showed up that day; messages==0 means inactive.
            active = 1.0 if (m is None or m > 0) else 0.0
            if active:
                rows.append({"date": d, "user_id": email, "metric": "active", "value": 1.0})
            if m is not None:
                rows.append({"date": d, "user_id": email, "metric": "messages", "value": m})
    elif period_col:
        starts = to_dates(df[period_col])
        end_col = pick_col(df, PERIOD_END_ALIASES)
        ends = to_dates(df[end_col]) if end_col else None
        days_col = pick_col(df, ACTIVE_DAYS_ALIASES)
        if not days_col and not msg_col:
            raise IngestError(
                "Period-grain export needs an active_days or messages column; "
                f"found columns {list(df.columns)}"
            )
        days = numeric(df[days_col]) if days_col else None
        msgs = numeric(df[msg_col]) if msg_col else None
        first_col = pick_col(df, FIRST_ACTIVE_ALIASES)
        last_col = pick_col(df, LAST_ACTIVE_ALIASES)
        created_col = pick_col(df, CREATED_ALIASES)
        firsts = to_dates(df[first_col]) if first_col else None
        lasts = to_dates(df[last_col]) if last_col else None
        createds = to_dates(df[created_col]) if created_col else None

        for i in range(len(df)):
            d = starts.iloc[i]
            if not valid_date(d):
                continue
            email = df[email_col].iloc[i]
            p_end = ends.iloc[i] if ends is not None else None
            if valid_date(p_end) and (p_end - d).days > LONG_PERIOD_DAYS:
                rows.extend(
                    _spread_row(
                        email,
                        msgs.iloc[i] if msgs is not None else None,
                        d,
                        p_end,
                        firsts.iloc[i] if firsts is not None else None,
                        lasts.iloc[i] if lasts is not None else None,
                        createds.iloc[i] if createds is not None else None,
                    )
                )
                continue
            if days is not None and pd.notna(days.iloc[i]) and days.iloc[i] > 0:
                rows.append(
                    {"date": d, "user_id": email, "metric": "active_days",
                     "value": float(days.iloc[i])}
                )
            if msgs is not None and pd.notna(msgs.iloc[i]):
                rows.append(
                    {"date": d, "user_id": email, "metric": "messages",
                     "value": float(msgs.iloc[i])}
                )
    else:
        raise IngestError(
            f"Need a date column ({DATE_ALIASES}) or a period column ({PERIOD_ALIASES}); "
            f"found columns {list(df.columns)}"
        )
    return make_facts(rows)
