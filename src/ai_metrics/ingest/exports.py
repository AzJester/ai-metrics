"""Per-vendor CSV export parsers. Each returns a facts DataFrame
(date, user_id, metric, value); tool_id is attached at upsert time.

Column names are matched after header normalization, so 'Period Start' and
'period_start' both work. If a vendor changes an export format, extend the
alias lists rather than editing the parse logic.
"""

from __future__ import annotations

import warnings

import pandas as pd

from . import peruser_chat
from .base import (
    make_facts,
    normalize_headers,
    numeric,
    pick_col,
    require_col,
    to_dates,
    valid_date,
)

CHATGPT_MESSAGE_ALIASES = ["messages", "message_count", "messages_sent", "total_messages", "prompts"]
CLAUDE_MESSAGE_ALIASES = ["messages", "conversations", "chats", "prompts", "message_count"]


def parse_chatgpt(df: pd.DataFrame) -> pd.DataFrame:
    """ChatGPT Enterprise workspace analytics export (per-user)."""
    return peruser_chat.parse(df, CHATGPT_MESSAGE_ALIASES)


def parse_claude(df: pd.DataFrame) -> pd.DataFrame:
    """Claude Team analytics export (per-user)."""
    return peruser_chat.parse(df, CLAUDE_MESSAGE_ALIASES)


def parse_copilot(df: pd.DataFrame) -> pd.DataFrame:
    """Copilot activity CSV (e.g. assembled from self-reports, or a future
    Metrics API dump): email, date, [active], [accepted_suggestions]."""
    df = normalize_headers(df)
    email_col = require_col(df, peruser_chat.EMAIL_ALIASES, "user email")
    date_col = require_col(df, peruser_chat.DATE_ALIASES, "date")
    active_col = pick_col(df, ["active", "was_active", "is_active"])
    acc_col = pick_col(df, ["accepted_suggestions", "suggestions_accepted", "acceptances"])

    dates = to_dates(df[date_col])
    active = numeric(df[active_col]) if active_col else None
    acc = numeric(df[acc_col]) if acc_col else None
    rows = []
    for i in range(len(df)):
        d = dates.iloc[i]
        if not valid_date(d):
            continue
        email = df[email_col].iloc[i]
        a = float(active.iloc[i]) if active is not None and pd.notna(active.iloc[i]) else 1.0
        if a > 0:
            rows.append({"date": d, "user_id": email, "metric": "active", "value": 1.0})
        if acc is not None and pd.notna(acc.iloc[i]):
            rows.append(
                {"date": d, "user_id": email, "metric": "accepted_suggestions",
                 "value": float(acc.iloc[i])}
            )
    return make_facts(rows)


def parse_rovo(df: pd.DataFrame) -> pd.DataFrame:
    """Rovo trends export (org-level): date, [app], [active_users], [actions].

    Active users: prefers an 'All'/'Overall' app row; otherwise takes the max
    across apps per date (a lower bound, since users overlap apps) and warns.
    Actions sum across apps.
    """
    df = normalize_headers(df)
    date_col = require_col(df, ["date", "day", "week", "period_start"], "date")
    app_col = pick_col(df, ["app", "product", "application"])
    au_col = pick_col(df, ["active_users", "users", "monthly_active_users", "daily_active_users"])
    act_col = pick_col(
        df, ["actions", "ai_interactions", "interactions", "agent_actions", "queries"]
    )

    df["_date"] = to_dates(df[date_col])
    df = df[df["_date"].notna()]
    rows = []
    overall_apps = {"all", "overall", "total", "all apps", "all_apps"}

    for d, grp in df.groupby("_date"):
        if au_col:
            au = numeric(grp[au_col])
            if app_col:
                is_overall = grp[app_col].astype(str).str.strip().str.lower().isin(overall_apps)
                if is_overall.any():
                    val = au[is_overall].max()
                else:
                    val = au.max()
                    warnings.warn(
                        "Rovo export has per-app rows but no 'All' row for "
                        f"{d}; using max across apps as a lower bound on active users.",
                        stacklevel=2,
                    )
            else:
                val = au.max()
            if pd.notna(val):
                rows.append({"date": d, "user_id": "", "metric": "active_users",
                             "value": float(val)})
        if act_col:
            total = numeric(grp[act_col]).sum()
            if pd.notna(total):
                rows.append({"date": d, "user_id": "", "metric": "actions",
                             "value": float(total)})
    return make_facts(rows)


def parse_pwin(df: pd.DataFrame) -> pd.DataFrame:
    """pWin.ai vendor report: email, date, drafts, [documents]."""
    df = normalize_headers(df)
    email_col = require_col(df, peruser_chat.EMAIL_ALIASES, "user email")
    date_col = require_col(df, peruser_chat.DATE_ALIASES, "date")
    drafts_col = require_col(
        df, ["drafts", "drafts_generated", "proposal_drafts", "generated_drafts"], "drafts"
    )
    docs_col = pick_col(df, ["documents", "documents_processed", "docs"])

    dates = to_dates(df[date_col])
    drafts = numeric(df[drafts_col])
    docs = numeric(df[docs_col]) if docs_col else None
    rows = []
    for i in range(len(df)):
        d = dates.iloc[i]
        if not valid_date(d):
            continue
        email = df[email_col].iloc[i]
        dr = drafts.iloc[i]
        if pd.notna(dr) and dr > 0:
            rows.append({"date": d, "user_id": email, "metric": "drafts", "value": float(dr)})
            rows.append({"date": d, "user_id": email, "metric": "active", "value": 1.0})
        if docs is not None and pd.notna(docs.iloc[i]):
            rows.append({"date": d, "user_id": email, "metric": "documents",
                         "value": float(docs.iloc[i])})
    return make_facts(rows)


def parse_icertis(df: pd.DataFrame) -> pd.DataFrame:
    """Icertis AI usage report: date, [email], agreements_ai_reviewed.

    Rows without an email become org-level aggregates.
    """
    df = normalize_headers(df)
    date_col = require_col(df, peruser_chat.DATE_ALIASES, "date")
    agr_col = require_col(
        df,
        ["agreements_ai_reviewed", "ai_reviews", "agreements_reviewed", "ai_agreements"],
        "agreements AI-reviewed",
    )
    email_col = pick_col(df, peruser_chat.EMAIL_ALIASES)

    dates = to_dates(df[date_col])
    agr = numeric(df[agr_col])
    rows = []
    for i in range(len(df)):
        d = dates.iloc[i]
        if not valid_date(d):
            continue
        a = agr.iloc[i]
        if pd.isna(a) or a <= 0:
            continue
        email = df[email_col].iloc[i] if email_col else ""
        rows.append({"date": d, "user_id": email, "metric": "agreements_ai_reviewed",
                     "value": float(a)})
        if email_col:
            rows.append({"date": d, "user_id": email, "metric": "active", "value": 1.0})
    return make_facts(rows)
