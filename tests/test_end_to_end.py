"""Full demo flow: sample data -> ingest -> KPI views populated."""

from pathlib import Path

from ai_metrics import report, sample_data
from ai_metrics.ingest import run_drop_ingest


def test_sample_pipeline(con, tmp_path, capsys):
    drop = tmp_path / "drop"
    written = sample_data.generate(drop)
    assert len(written) == 8

    results = run_drop_ingest(con, drop, archive=True, archive_dir=tmp_path / "processed")
    assert all("loaded" in outcome for _, outcome in results), results
    # Files were archived out of the drop folder.
    assert not list(Path(drop).glob("*.csv"))

    months = con.execute("SELECT COUNT(DISTINCT month) FROM kpi_adoption_monthly").fetchone()[0]
    assert months == 2  # April + May 2026

    tools = {
        r[0] for r in con.execute("SELECT DISTINCT tool_id FROM kpi_adoption_monthly").fetchall()
    }
    assert {"chatgpt", "claude", "copilot", "rovo", "pwin", "icertis"} <= tools

    roi_rows = con.execute("SELECT COUNT(*) FROM kpi_roi_monthly").fetchone()[0]
    assert roi_rows > 0

    # Console report renders without error.
    report.print_report(con)
    out = capsys.readouterr().out
    assert "Adoption" in out and "ROI" in out

    # Curated export writes every table.
    out_dir = tmp_path / "curated"
    files = report.export_curated(con, out_dir)
    assert len(files) == len(report.CURATED_TABLES)
    assert all(f.exists() and f.stat().st_size > 0 for f in files)
