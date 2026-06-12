"""GitHub Copilot Metrics API connector (org-level aggregates).

Requires GITHUB_TOKEN (or GH_TOKEN) with read:org / manage_billing:copilot
scope and GITHUB_ORG. Only works on Copilot Business/Enterprise; Copilot
Free reports nothing, which is why this connector emits org-level rows only
when the API responds. Reference:
https://docs.github.com/en/rest/copilot/copilot-metrics
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import httpx
import pandas as pd

from ..base import make_facts


def fetch(days: int = 30) -> pd.DataFrame | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    org = os.environ.get("GITHUB_ORG")
    if not token or not org:
        return None
    base = os.environ.get("GITHUB_API_BASE", "https://api.github.com")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    since = (date.today() - timedelta(days=min(days, 27))).isoformat()  # API max: 28 days

    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{base}/orgs/{org}/copilot/metrics",
            headers=headers,
            params={"since": since},
        )
        resp.raise_for_status()
        items = resp.json()

    rows = []
    for item in items:
        d = date.fromisoformat(str(item.get("date"))[:10])
        if item.get("total_active_users") is not None:
            rows.append({"date": d, "user_id": "", "metric": "active_users",
                         "value": float(item["total_active_users"])})
        if item.get("total_engaged_users") is not None:
            rows.append({"date": d, "user_id": "", "metric": "engaged_users",
                         "value": float(item["total_engaged_users"])})
    return make_facts(rows)
