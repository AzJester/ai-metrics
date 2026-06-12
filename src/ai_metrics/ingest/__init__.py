"""Drop-folder ingestion: routes data/drop/*.csv to a parser by filename
prefix, loads facts, then archives the file under data/raw/processed/.

Prefix conventions (longest match wins):
  roster_*.csv       HR roster -> dim_user
  survey_*.csv       pulse survey -> fact_survey
  chatgpt_*.csv      ChatGPT Enterprise per-user analytics export
  claude_code_*.csv  Claude Code per-user activity
  claude_*.csv       Claude Team per-user analytics export
  copilot_*.csv      Copilot activity
  rovo_*.csv         Rovo trends export (org-level)
  pwin_*.csv         pWin.ai vendor report
  icertis_*.csv      Icertis AI usage report
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import duckdb
import pandas as pd

from . import exports, roster, survey
from .base import IngestError, upsert_facts

DEFAULT_DROP_DIR = Path("data/drop")
DEFAULT_ARCHIVE_DIR = Path("data/raw/processed")

# prefix -> (tool_id, parser). Checked longest-prefix-first.
FACT_PARSERS = {
    "chatgpt": ("chatgpt", exports.parse_chatgpt),
    "claude_code": ("claude_code", exports.parse_claude),
    "claude": ("claude", exports.parse_claude),
    "copilot": ("copilot", exports.parse_copilot),
    "rovo": ("rovo", exports.parse_rovo),
    "pwin": ("pwin", exports.parse_pwin),
    "icertis": ("icertis", exports.parse_icertis),
}


def route(filename: str):
    """Return ('fact', tool_id, parser) | ('roster',) | ('survey',) | None."""
    stem = Path(filename).stem.lower()
    if stem.startswith("roster"):
        return ("roster",)
    if stem.startswith("survey"):
        return ("survey",)
    for prefix in sorted(FACT_PARSERS, key=len, reverse=True):
        if stem.startswith(prefix):
            tool_id, parser = FACT_PARSERS[prefix]
            return ("fact", tool_id, parser)
    return None


def ingest_file(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    routed = route(path.name)
    if routed is None:
        raise IngestError(
            f"{path.name}: unrecognized prefix. Expected one of: roster_, survey_, "
            + ", ".join(f"{p}_" for p in FACT_PARSERS)
        )
    df = pd.read_csv(path)
    if routed[0] == "roster":
        return roster.ingest(con, df, path.name)
    if routed[0] == "survey":
        return survey.ingest(con, df, path.name)
    _, tool_id, parser = routed
    facts = parser(df)
    return upsert_facts(con, facts, tool_id, source=f"{tool_id}_export", file_or_run=path.name)


def run_drop_ingest(
    con: duckdb.DuckDBPyConnection,
    drop_dir: Path = DEFAULT_DROP_DIR,
    archive: bool = True,
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
) -> list[tuple[str, str]]:
    """Ingest every CSV in the drop folder. Returns [(filename, outcome)].

    Roster files are ingested first so department joins see fresh data.
    Unrecognized or failing files are left in place and reported, never
    silently dropped.
    """
    results: list[tuple[str, str]] = []
    files = sorted(drop_dir.glob("*.csv")) if drop_dir.is_dir() else []
    files.sort(key=lambda p: (route(p.name) != ("roster",), p.name))
    for path in files:
        try:
            n = ingest_file(con, path)
        except IngestError as e:
            results.append((path.name, f"SKIPPED: {e}"))
            continue
        if archive:
            archive_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%dT%H%M%S")
            shutil.move(str(path), archive_dir / f"{stamp}_{path.name}")
        results.append((path.name, f"loaded {n} rows"))
    return results
