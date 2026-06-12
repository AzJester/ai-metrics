"""ChatGPT Enterprise Compliance API connector. EXPERIMENTAL.

Requires OPENAI_ADMIN_API_KEY and OPENAI_WORKSPACE_ID, and Compliance API
enablement on the workspace. Endpoint shapes vary by enablement and OpenAI
migrated to the Compliance Logs Platform in 2026; verify the base URL and
paths against your workspace's docs and adjust OPENAI_COMPLIANCE_API_BASE
if needed.

Privacy: this connector reads conversation METADATA ONLY (user, timestamp)
to build daily activity counts. Content fields are never inspected or
stored. Keep it that way.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import httpx
import pandas as pd

from ..base import make_facts


def _user_email(conv: dict, users: dict) -> str:
    uid = conv.get("user_id") or conv.get("owner_id") or ""
    return users.get(uid, conv.get("user_email", "") or "")


def _fetch_users(client: httpx.Client, base: str, ws: str, headers: dict) -> dict:
    """Map workspace user ids -> emails."""
    users: dict[str, str] = {}
    after = None
    while True:
        params = {"limit": 200}
        if after:
            params["after"] = after
        resp = client.get(f"{base}/compliance/workspaces/{ws}/users",
                          headers=headers, params=params)
        resp.raise_for_status()
        payload = resp.json()
        for u in payload.get("data", []):
            if u.get("id") and u.get("email"):
                users[u["id"]] = u["email"]
        if payload.get("has_more") and payload.get("last_id"):
            after = payload["last_id"]
        else:
            return users


def fetch(days: int = 30) -> pd.DataFrame | None:
    key = os.environ.get("OPENAI_ADMIN_API_KEY")
    ws = os.environ.get("OPENAI_WORKSPACE_ID")
    if not key or not ws:
        return None
    base = os.environ.get("OPENAI_COMPLIANCE_API_BASE", "https://api.chatgpt.com/v1")
    headers = {"Authorization": f"Bearer {key}"}
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    convs_per_user_day: Counter = Counter()
    with httpx.Client(timeout=60) as client:
        users = _fetch_users(client, base, ws, headers)
        after = None
        while True:
            params = {"since_timestamp": since, "limit": 200}
            if after:
                params["after"] = after
            resp = client.get(f"{base}/compliance/workspaces/{ws}/conversations",
                              headers=headers, params=params)
            resp.raise_for_status()
            payload = resp.json()
            for conv in payload.get("data", []):
                ts = conv.get("last_active_at") or conv.get("created_at")
                if ts is None:
                    continue
                d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
                email = _user_email(conv, users)
                if email:
                    convs_per_user_day[(email, d)] += 1
            if payload.get("has_more") and payload.get("last_id"):
                after = payload["last_id"]
            else:
                break

    rows = []
    seen_active: set[tuple[str, date]] = set()
    for (email, d), n in sorted(convs_per_user_day.items()):
        if (email, d) not in seen_active:
            rows.append({"date": d, "user_id": email, "metric": "active", "value": 1.0})
            seen_active.add((email, d))
        rows.append({"date": d, "user_id": email, "metric": "conversations", "value": float(n)})
    return make_facts(rows)
