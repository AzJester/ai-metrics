"""Command-line interface.

  ai-metrics init           create/refresh warehouse from config
  ai-metrics sample-data    write demo CSVs into the drop folder
  ai-metrics ingest         process drop-folder CSVs + configured API connectors
  ai-metrics report         print KPI summary for the latest (or given) month
  ai-metrics export         write curated KPI tables to CSV for Power BI
  ai-metrics dashboard      launch the Streamlit dashboard
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import __version__, db, ingest, report, sample_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-metrics", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create/refresh the warehouse from config")

    p = sub.add_parser("sample-data", help="write demo CSVs into the drop folder")
    p.add_argument("--out", type=Path, default=ingest.DEFAULT_DROP_DIR)

    p = sub.add_parser("ingest", help="ingest drop-folder CSVs and API connectors")
    p.add_argument("--drop-dir", type=Path, default=ingest.DEFAULT_DROP_DIR)
    p.add_argument("--no-archive", action="store_true",
                   help="leave processed files in the drop folder")
    p.add_argument("--skip-apis", action="store_true", help="skip API connectors")
    p.add_argument("--days", type=int, default=30, help="API lookback window (days)")

    p = sub.add_parser("report", help="print KPI summary")
    p.add_argument("--month", help="month start date, e.g. 2026-05-01 (default: latest)")

    p = sub.add_parser("export", help="write curated KPI tables to CSV")
    p.add_argument("--out", type=Path, default=Path("data/curated"))

    sub.add_parser("dashboard", help="launch the Streamlit dashboard")

    args = parser.parse_args(argv)

    if args.command == "init":
        con = db.connect_and_init()
        con.close()
        print(f"Warehouse ready at {db.db_path()}")
        return 0

    if args.command == "sample-data":
        written = sample_data.generate(args.out)
        for path in written:
            print(f"wrote {path}")
        print(f"\n{len(written)} sample files written. Next: ai-metrics ingest")
        return 0

    if args.command == "ingest":
        con = db.connect_and_init()
        results = ingest.run_drop_ingest(con, args.drop_dir, archive=not args.no_archive)
        if not args.skip_apis:
            from .ingest import api

            results += api.run_all(con, days=args.days)
        con.close()
        if not results:
            print(f"Nothing to ingest: no CSVs in {args.drop_dir} and no API credentials set.")
            return 0
        failed = 0
        for name, outcome in results:
            print(f"  {name}: {outcome}")
            if outcome.startswith(("SKIPPED", "FAILED")):
                failed += 1
        return 1 if failed else 0

    if args.command == "report":
        con = db.connect_and_init()
        report.print_report(con, month=args.month)
        con.close()
        return 0

    if args.command == "export":
        con = db.connect_and_init()
        written = report.export_curated(con, args.out)
        con.close()
        for path in written:
            print(f"wrote {path}")
        return 0

    if args.command == "dashboard":
        app = Path(__file__).resolve().parents[2] / "dashboard" / "app.py"
        if not app.exists():
            app = Path("dashboard/app.py")
        return subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app)], check=False
        ).returncode

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
