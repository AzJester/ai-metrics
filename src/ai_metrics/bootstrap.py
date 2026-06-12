"""Self-bootstrap for hosted deployments (e.g. Streamlit Community Cloud).

Cloud hosts get a fresh filesystem on every boot, so the warehouse must be
rebuildable from what's in the repo: committed CSVs in data/public/ if
present, generated sample data otherwise.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def ensure_warehouse(repo_root: Path) -> tuple[Path, str]:
    """Create the warehouse if it doesn't exist. Returns (db_path, mode)
    where mode is 'existing', 'public' (built from data/public/ CSVs), or
    'sample' (built from generated demo data)."""
    repo_root = Path(repo_root)
    db_path = Path(os.environ.get("AI_METRICS_DB", repo_root / "data" / "warehouse.duckdb"))
    os.environ.setdefault("AI_METRICS_DB", str(db_path))
    os.environ.setdefault("AI_METRICS_CONFIG_DIR", str(repo_root / "config"))

    if db_path.exists():
        return db_path, "existing"

    from . import db, sample_data
    from .ingest import run_drop_ingest

    con = db.connect_and_init()
    try:
        public_dir = repo_root / "data" / "public"
        if public_dir.is_dir() and list(public_dir.glob("*.csv")):
            run_drop_ingest(con, public_dir, archive=False)
            mode = "public"
        else:
            with tempfile.TemporaryDirectory() as tmp:
                drop = Path(tmp)
                sample_data.generate(drop)
                run_drop_ingest(con, drop, archive=False)
            mode = "sample"
    finally:
        con.close()
    return db_path, mode
