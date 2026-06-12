import shutil
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def con(tmp_path, monkeypatch) -> duckdb.DuckDBPyConnection:
    """Fresh warehouse in a temp dir, seeded from the real config files."""
    config_dir = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config", config_dir)
    monkeypatch.setenv("AI_METRICS_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("AI_METRICS_DB", str(tmp_path / "warehouse.duckdb"))

    from ai_metrics import db

    connection = db.connect_and_init()
    yield connection
    connection.close()
