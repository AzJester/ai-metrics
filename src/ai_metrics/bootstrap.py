"""Self-bootstrap for hosted deployments (e.g. Streamlit Community Cloud).

Cloud hosts get a fresh filesystem on every boot, so the warehouse must be
rebuildable from what's in the repo: committed CSVs in data/public/ if
present, generated sample data otherwise.

Staleness: hosts that update code via git pull KEEP the filesystem, so an
existing warehouse may have been built from older data or config. A
fingerprint of the source inputs (config files + data/public CSVs) is stored
in the warehouse at build time; on boot, a mismatch triggers a rebuild. This
is what makes "push new CSVs, dashboard updates" hold on every host.

Concurrency: at boot, several script runs can race to build the warehouse
(Streamlit's health checker plus the first visitors). Each builder therefore
writes to its own unique temp file and atomically renames it into place;
concurrent builders produce identical content, so whichever rename lands
last is fine, and no two writers ever touch the same DuckDB file.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from pathlib import Path

FINGERPRINT_KEY = "source_fingerprint"


def _source_fingerprint(repo_root: Path) -> str:
    h = hashlib.sha256()
    config_dir = Path(os.environ.get("AI_METRICS_CONFIG_DIR", repo_root / "config"))
    public_dir = repo_root / "data" / "public"
    files = sorted(config_dir.glob("*.yaml")) + sorted(
        public_dir.glob("*.csv") if public_dir.is_dir() else []
    )
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def _stored_fingerprint(db_path: Path) -> str | None:
    import duckdb

    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception:
        # Locked by a concurrent builder or unreadable: leave it alone.
        return None
    try:
        row = con.execute(
            "SELECT value FROM config_kv WHERE key = ?", [FINGERPRINT_KEY]
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        con.close()


def ensure_warehouse(repo_root: Path) -> tuple[Path, str]:
    """Create the warehouse if it doesn't exist or its sources changed.
    Returns (db_path, mode): 'existing' (fresh enough), 'public' (built from
    data/public/ CSVs), or 'sample' (built from generated demo data)."""
    repo_root = Path(repo_root)
    db_path = Path(os.environ.get("AI_METRICS_DB", repo_root / "data" / "warehouse.duckdb"))
    os.environ.setdefault("AI_METRICS_DB", str(db_path))
    os.environ.setdefault("AI_METRICS_CONFIG_DIR", str(repo_root / "config"))

    fingerprint = _source_fingerprint(repo_root)
    if db_path.exists() and _stored_fingerprint(db_path) == fingerprint:
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
        con.execute(
            "INSERT OR REPLACE INTO config_kv (key, value) VALUES (?, ?)",
            [FINGERPRINT_KEY, fingerprint],
        )
    finally:
        con.close()

    os.replace(tmp_db, db_path)
    return db_path, mode
