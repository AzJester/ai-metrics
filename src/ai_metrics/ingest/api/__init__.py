"""API connectors. Each connector activates only when its environment
variables are set, so `ai-metrics ingest` is safe to run anywhere.

  openai_compliance : OPENAI_ADMIN_API_KEY, OPENAI_WORKSPACE_ID
  claude_code       : ANTHROPIC_ADMIN_KEY
  copilot_metrics   : GITHUB_TOKEN (or GH_TOKEN), GITHUB_ORG
"""

from __future__ import annotations

import traceback

import duckdb

from ..base import upsert_facts
from . import claude_code, copilot_metrics, openai_compliance

CONNECTORS = [
    ("chatgpt", "openai_api", openai_compliance.fetch),
    ("claude_code", "claude_code_api", claude_code.fetch),
    ("copilot", "copilot_api", copilot_metrics.fetch),
]


def run_all(con: duckdb.DuckDBPyConnection, days: int = 30) -> list[tuple[str, str]]:
    results = []
    for tool_id, source, fetch in CONNECTORS:
        try:
            facts = fetch(days=days)
        except Exception as e:  # a broken vendor API must not block other sources
            traceback.print_exc()
            results.append((source, f"FAILED: {e}"))
            continue
        if facts is None:
            results.append((source, "skipped (credentials not configured)"))
            continue
        n = upsert_facts(con, facts, tool_id, source=source, file_or_run=f"{source}:last{days}d")
        results.append((source, f"loaded {n} rows"))
    return results
