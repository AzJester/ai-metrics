# ai-metrics

Ingestion pipeline and KPI dashboard for enterprise AI tool usage (ChatGPT
Enterprise, Claude Team, GitHub Copilot, Atlassian Rovo, Icertis, pWin.ai):
adoption, estimated hours saved, and ROI.

See [PLAN.md](PLAN.md) for the full design: per-vendor data availability, KPI
definitions, the hours-saved/ROI methodology, architecture, and roadmap.

## Quickstart (demo with sample data)

```bash
pip install -e ".[dashboard]"
ai-metrics init           # create the DuckDB warehouse from config/
ai-metrics sample-data    # write demo CSVs into data/drop/
ai-metrics ingest         # load them (and any configured API sources)
ai-metrics report         # console KPI summary
ai-metrics dashboard      # Streamlit dashboard at localhost:8501
```

## Using real data

### 1. Configure tools and assumptions

- `config/tools.yaml`: licensed seats and monthly cost per tool (drives
  activation rate and ROI), plus the blended burdened hourly rate.
- `config/multipliers.yaml`: minutes saved per unit of activity, as
  conservative/expected pairs. Versioned; bump the version when you
  recalibrate so history stays auditable.

### 2. Drop CSV exports into `data/drop/`

Files route by filename prefix. Headers are case/punctuation-insensitive and
common vendor variants are accepted (see alias lists in
`src/ai_metrics/ingest/`):

| Prefix | Source | Expected columns |
|---|---|---|
| `roster_` | HR roster | email, name, department, role_family, burdened_rate, active |
| `chatgpt_` | ChatGPT Enterprise workspace analytics export | email, date, messages (daily) or email, period_start, active_days, messages |
| `claude_` | Claude Team analytics export | same shapes as chatgpt |
| `claude_code_` | Claude Code activity | same shapes as chatgpt |
| `copilot_` | Copilot activity | email, date, active, accepted_suggestions |
| `rovo_` | Rovo trends export | date, app, active_users, actions |
| `pwin_` | pWin.ai vendor report | email, date, drafts, documents |
| `icertis_` | Icertis AI usage report | date, email, agreements_ai_reviewed |
| `survey_` | Quarterly pulse survey | timestamp, email, tools_used, weekly_time_saved_band, top_task, copilot_days_per_week, dependence |

`ai-metrics ingest` loads everything, archives processed files to
`data/raw/processed/`, and is idempotent: re-ingesting an overlapping export
replaces rows instead of double counting.

### 3. Optional: automated API pulls

Connectors activate when their environment variables are set:

| Connector | Env vars | Notes |
|---|---|---|
| ChatGPT Enterprise Compliance API | `OPENAI_ADMIN_API_KEY`, `OPENAI_WORKSPACE_ID` | Experimental; verify endpoints against your workspace's enablement. Logs retain ~30 days, so run daily. |
| Claude Code Analytics API | `ANTHROPIC_ADMIN_KEY` | Admin API key (`sk-ant-admin...`). |
| Copilot Metrics API | `GITHUB_TOKEN`, `GITHUB_ORG` | Requires Copilot Business/Enterprise; Copilot Free has no API. |

A scheduled GitHub Actions workflow (`.github/workflows/ingest.yml`) runs
these daily once secrets are configured.

### 4. Reporting

- `ai-metrics report` prints the monthly KPI summary.
- `ai-metrics dashboard` serves the Streamlit dashboard (executive overview,
  adoption, efficiency & ROI, methodology/data quality).
- `ai-metrics export` writes the KPI views to `data/curated/*.csv` for
  Power BI. Power BI can also query `data/warehouse.duckdb` directly; either
  way the KPI definitions live in `src/ai_metrics/views.sql`, not in BI
  formulas.

## Hosting the dashboard on the web (Streamlit Community Cloud)

To give end users a permanent URL, deploy the dashboard to Streamlit
Community Cloud (free, hosts straight from this repo):

1. Go to <https://share.streamlit.io> and sign in with the GitHub account
   that owns this repo.
2. **Create app** → **Deploy a public app from GitHub** → repository
   `AzJester/ai-metrics`, branch `main`, main file path `dashboard/app.py`.
3. Deploy. The app gets a permanent `https://<name>.streamlit.app` URL you
   can share.

On boot the app builds its warehouse from CSVs committed to
[`data/public/`](data/public/README.md) (same prefixes/columns as
`data/drop/`). With no files there it falls back to generated demo data and
shows a banner. Pushing new CSVs to the deployed branch redeploys the app
automatically.

Notes:
- The URL is public to anyone who has it. To limit who can open it, use the
  app's **Settings → Sharing** to require viewers to log in with allowed
  email addresses.
- Community Cloud apps sleep after a few days without visitors; the first
  visit wakes them in ~30 seconds.

## Privacy

The pipeline ingests usage **metadata only**: who used which tool on which
day, and how much. Prompt and conversation content is never requested,
parsed, or stored. Exports contain employee emails, so `data/` is gitignored
by default; the one exception is `data/public/`, which exists for usage data
explicitly deemed non-confidential and feeds the hosted dashboard. Default
dashboards aggregate by department.

## Development

```bash
pip install -e ".[dev]"
ruff check src tests
pytest
```

Warehouse location defaults to `data/warehouse.duckdb`; override with
`AI_METRICS_DB`. Config directory defaults to `config/`; override with
`AI_METRICS_CONFIG_DIR`.
