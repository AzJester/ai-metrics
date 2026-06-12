import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

from ai_metrics.bootstrap import ensure_warehouse

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fake_repo(tmp_path, monkeypatch):
    shutil.copytree(REPO_ROOT / "config", tmp_path / "config")
    monkeypatch.setenv("AI_METRICS_DB", str(tmp_path / "data" / "warehouse.duckdb"))
    monkeypatch.setenv("AI_METRICS_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path


def test_bootstrap_falls_back_to_sample_data(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path, monkeypatch)
    db_path, mode = ensure_warehouse(root)
    assert mode == "sample"
    assert db_path.exists()
    con = duckdb.connect(str(db_path), read_only=True)
    assert con.execute("SELECT COUNT(*) FROM fact_usage_daily").fetchone()[0] > 0
    con.close()

    # Second call reuses the existing warehouse.
    _, mode2 = ensure_warehouse(root)
    assert mode2 == "existing"


def test_bootstrap_concurrent_cold_start(tmp_path, monkeypatch):
    """Concurrent boots (Streamlit health check + first visitors) must not
    hit DuckDB write-write conflicts; each builder uses its own temp file."""
    root = _fake_repo(tmp_path, monkeypatch)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ensure_warehouse(root), range(4)))
    assert all(path.exists() for path, _ in results)
    assert {mode for _, mode in results} <= {"sample", "existing"}
    # No leftover temp files from losing builders.
    assert not list((root / "data").glob(".*tmp*"))
    con = duckdb.connect(str(results[0][0]), read_only=True)
    assert con.execute("SELECT COUNT(*) FROM fact_usage_daily").fetchone()[0] > 0
    con.close()


def test_bootstrap_rebuilds_when_sources_change(tmp_path, monkeypatch):
    """A warehouse built from older data/config must be rebuilt, not reused:
    hosts that git-pull code updates keep the filesystem."""
    root = _fake_repo(tmp_path, monkeypatch)
    db_path, mode = ensure_warehouse(root)
    assert mode == "sample"

    # New data lands in data/public -> next boot rebuilds from it.
    public = root / "data" / "public"
    public.mkdir(parents=True)
    (public / "chatgpt_new.csv").write_text("email,date,messages\na@x.com,2026-05-04,7\n")
    db_path2, mode2 = ensure_warehouse(root)
    assert mode2 == "public"
    con = duckdb.connect(str(db_path2), read_only=True)
    tools = {r[0] for r in con.execute("SELECT DISTINCT tool_id FROM fact_usage_daily").fetchall()}
    assert tools == {"chatgpt"}  # old sample data fully replaced
    con.close()

    # Unchanged sources -> reused.
    _, mode3 = ensure_warehouse(root)
    assert mode3 == "existing"

    # Config edits also trigger a rebuild.
    cfg = root / "config" / "tools.yaml"
    cfg.write_text(cfg.read_text().replace("licensed_seats: 201", "licensed_seats: 250"))
    _, mode4 = ensure_warehouse(root)
    assert mode4 == "public"


def test_bootstrap_prefers_public_dir(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path, monkeypatch)
    public = root / "data" / "public"
    public.mkdir(parents=True)
    (public / "chatgpt_real.csv").write_text(
        "email,date,messages\na@x.com,2026-05-04,7\n"
    )
    db_path, mode = ensure_warehouse(root)
    assert mode == "public"
    con = duckdb.connect(str(db_path), read_only=True)
    tools = {r[0] for r in con.execute("SELECT DISTINCT tool_id FROM fact_usage_daily").fetchall()}
    assert tools == {"chatgpt"}  # no sample data mixed in
    # File stays in place (archive=False) for the next redeploy.
    assert (public / "chatgpt_real.csv").exists()
    con.close()
