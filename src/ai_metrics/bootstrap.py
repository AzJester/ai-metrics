"""Self-bootstrap for hosted deployments (e.g. Streamlit Community Cloud).

Cloud hosts get a fresh filesystem on every boot, so the warehouse must be
rebuildable from what's in the repo: committed CSVs in data/public/ if
present, generated sample data otherwise.

Concurrency: at boot, several script runs can race to build the warehouse
(Streamlit's health checker plus the first visitors). Each builder therefore
writes to its own unique temp file and atomically renames it into place;
concurrent builders produce identical content, so whichever rename lands
last is fine, and no two writers ever touch the same DuckDB file.
"""

from __future__ import annotations

import os
import tempfile
import uuid
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

    tmp_db = db_path.with_name(f".{db_path.name}.{uuid.uuid4().hex}.tmp")
    con = db.connect(path=tmp_db)
    try:
        db.init_db(con)
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

    if db_path.exists():
        # A concurrent builder won the race; its warehouse is equivalent.
        tmp_db.unlink(missing_ok=True)
        return db_path, "existing"
    os.replace(tmp_db, db_path)
    return db_path, mode
