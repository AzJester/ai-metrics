"""Deterministic sample data so the pipeline runs end to end out of the box.

Writes one CSV per source into the drop folder, covering April-May 2026 for
a fictional 12-person slice of the company. Run `ai-metrics sample-data`,
then `ai-metrics ingest`.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

START = date(2026, 4, 1)
END = date(2026, 5, 31)

# (email, name, department, role_family, burdened_rate)
USERS = [
    ("alice.barnes@example.com", "Alice Barnes", "Business Development", "BD", 90),
    ("ben.ortiz@example.com", "Ben Ortiz", "Business Development", "BD", 90),
    ("chen.wei@example.com", "Chen Wei", "Engineering", "Engineering", 95),
    ("dana.kim@example.com", "Dana Kim", "Engineering", "Engineering", 95),
    ("eric.lopez@example.com", "Eric Lopez", "Engineering", "Engineering", 95),
    ("fatima.shah@example.com", "Fatima Shah", "Engineering", "Engineering", 95),
    ("grace.liu@example.com", "Grace Liu", "Legal", "Legal", 110),
    ("hank.moore@example.com", "Hank Moore", "Legal", "Legal", 110),
    ("iris.novak@example.com", "Iris Novak", "Contracts", "Contracts", 85),
    ("jay.patel@example.com", "Jay Patel", "Finance", "Finance", 80),
    ("kara.jones@example.com", "Kara Jones", "HR", "HR", 75),
    ("liam.reed@example.com", "Liam Reed", "IT", "IT", 85),
]

ENGINEERS = [u for u in USERS if u[2] == "Engineering"]
BD = [u for u in USERS if u[2] == "Business Development"]
LEGAL_CONTRACTS = [u for u in USERS if u[2] in ("Legal", "Contracts")]


def _weekdays():
    d = START
    while d <= END:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def generate(drop_dir: Path) -> list[Path]:
    rng = random.Random(42)
    drop_dir.mkdir(parents=True, exist_ok=True)
    written = []

    # Roster
    path = drop_dir / "roster_sample.csv"
    _write(
        path,
        ["email", "name", "department", "role_family", "burdened_rate", "active"],
        [[e, n, d, r, rate, "true"] for e, n, d, r, rate in USERS],
    )
    written.append(path)

    # ChatGPT: daily per-user rows
    rows = []
    activity = {u[0]: rng.uniform(0.3, 0.85) for u in USERS}
    for d in _weekdays():
        for email, *_ in USERS:
            if rng.random() < activity[email]:
                rows.append([email, d.isoformat(), rng.randint(2, 25)])
    path = drop_dir / "chatgpt_sample.csv"
    _write(path, ["email", "date", "messages"], rows)
    written.append(path)

    # Claude Team: monthly per-user rows (period grain)
    rows = []
    claude_users = USERS[2:8]
    for month_start in (date(2026, 4, 1), date(2026, 5, 1)):
        for email, *_ in claude_users:
            days = rng.randint(4, 18)
            rows.append([email, month_start.isoformat(), days, days * rng.randint(3, 9)])
    path = drop_dir / "claude_sample.csv"
    _write(path, ["email", "period_start", "active_days", "messages"], rows)
    written.append(path)

    # Copilot: daily per-engineer rows
    rows = []
    for d in _weekdays():
        for email, *_ in ENGINEERS:
            if rng.random() < 0.7:
                rows.append([email, d.isoformat(), 1, rng.randint(10, 80)])
    path = drop_dir / "copilot_sample.csv"
    _write(path, ["email", "date", "active", "accepted_suggestions"], rows)
    written.append(path)

    # Rovo: org-level rows per app per day, including an 'All' row
    rows = []
    for d in _weekdays():
        jira = rng.randint(15, 45)
        confluence = rng.randint(10, 35)
        total = max(jira, confluence) + rng.randint(5, 20)
        rows.append([d.isoformat(), "Jira", jira, jira * rng.randint(2, 5)])
        rows.append([d.isoformat(), "Confluence", confluence, confluence * rng.randint(2, 5)])
        rows.append([d.isoformat(), "All", total, (jira + confluence) * rng.randint(2, 5)])
    path = drop_dir / "rovo_sample.csv"
    _write(path, ["date", "app", "active_users", "actions"], rows)
    written.append(path)

    # pWin: BD users generate drafts roughly twice a week
    rows = []
    for d in _weekdays():
        for email, *_ in BD:
            if rng.random() < 0.35:
                rows.append([email, d.isoformat(), rng.randint(1, 3), rng.randint(2, 10)])
    path = drop_dir / "pwin_sample.csv"
    _write(path, ["email", "date", "drafts", "documents"], rows)
    written.append(path)

    # Icertis: Legal/Contracts users review agreements
    rows = []
    for d in _weekdays():
        for email, *_ in LEGAL_CONTRACTS:
            if rng.random() < 0.5:
                rows.append([email, d.isoformat(), rng.randint(1, 6)])
    path = drop_dir / "icertis_sample.csv"
    _write(path, ["email", "date", "agreements_ai_reviewed"], rows)
    written.append(path)

    # Survey: one wave, mid-May
    bands = ["<30 min", "30-60 min", "1-3 hrs", "3-8 hrs", "8+ hrs"]
    tool_sets = [
        "ChatGPT; Claude", "ChatGPT", "ChatGPT; GitHub Copilot", "Claude; Rovo",
        "ChatGPT; pWin.ai", "Icertis; ChatGPT", "GitHub Copilot; ChatGPT", "Rovo",
    ]
    rows = []
    for i, (email, *_rest) in enumerate(USERS[:10]):
        rows.append(
            [
                "2026-05-15",
                email,
                tool_sets[i % len(tool_sets)],
                bands[rng.randint(0, len(bands) - 1)],
                "drafting and summarizing documents",
                rng.randint(0, 5),
                "moderately",
            ]
        )
    path = drop_dir / "survey_sample.csv"
    _write(
        path,
        ["timestamp", "email", "tools_used", "weekly_time_saved_band", "top_task",
         "copilot_days_per_week", "dependence"],
        rows,
    )
    written.append(path)

    return written
