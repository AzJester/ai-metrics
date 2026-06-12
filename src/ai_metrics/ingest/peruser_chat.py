"""Generic parser for per-user chat-assistant exports (ChatGPT, Claude).

Accepts either grain:
- daily rows:   email, date, [messages]            -> 'active' + 'messages'
- period rows:  email, period_start, [active_days], [messages]
                                                   -> 'active_days' + 'messages'
"""

from __future__ import annotations

import pandas as pd

from .base import IngestError, make_facts, normalize_headers, numeric, pick_col, require_col, to_dates, valid_date

EMAIL_ALIASES = ["email", "user_email", "user", "member_email", "email_address"]
DATE_ALIASES = ["date", "day", "activity_date"]
PERIOD_ALIASES = ["period_start", "start_date", "week_start", "month_start", "period", "month"]
ACTIVE_DAYS_ALIASES = ["active_days", "days_active", "num_active_days"]


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
        dates = to_dates(df[period_col])
        days_col = pick_col(df, ACTIVE_DAYS_ALIASES)
        if not days_col and not msg_col:
            raise IngestError(
                "Period-grain export needs an active_days or messages column; "
                f"found columns {list(df.columns)}"
            )
        days = numeric(df[days_col]) if days_col else None
        msgs = numeric(df[msg_col]) if msg_col else None
        for i in range(len(df)):
            d = dates.iloc[i]
            if not valid_date(d):
                continue
            email = df[email_col].iloc[i]
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
