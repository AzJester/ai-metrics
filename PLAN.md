# AI Usage Metrics & ROI Dashboard: Implementation Plan

**Goal:** One dashboard that answers three questions for leadership, refreshed at least weekly:

1. **Adoption:** Who is using which AI tools, how often, and is it growing?
2. **Efficiency:** How many labor hours are these tools saving?
3. **ROI:** Is the value of those hours (plus business outcomes) worth what we pay?

The hard constraint is not the dashboard. It is that the six tools expose wildly different
levels of usage data, and "hours saved" is not directly measurable from any of them. The plan
below is built around those two realities.

---

## 1. Data availability by tool (the controlling constraint)

This determines what can be automated, what must be a recurring manual export, and what
requires surveys or vendor cooperation. Verified against vendor documentation as of June 2026.

| Tool | Usage data available | How to get it | Automation level |
|---|---|---|---|
| **ChatGPT Enterprise** | Active users (DAU/WAU/MAU), messages per user, GPT & tool usage breakdowns, usage by team/department, SSO-mapped identities | **Compliance Logs Platform / Compliance API** (JSONL log files, cursor-paginated) plus workspace analytics in the admin console (CSV export). Note: platform retention is **30 days**, so the pipeline must pull on a schedule and store history itself. | **Full** (scheduled API pull) |
| **Claude Team** | Org usage analytics (Owners/Primary Owner only; the plain Admin role cannot see analytics on Team), exportable reports; Claude Code usage via the **Claude Code Analytics API** (Admin API key, `sk-ant-admin...`) | Analytics page export (manual CSV) + Claude Code Analytics API if Claude Code is in use. The full per-user, all-surfaces **Enterprise Analytics API requires the Enterprise plan**, not Team. | **Partial** (API for Claude Code, monthly manual CSV for chat) |
| **GitHub Copilot Free** | **None centrally.** The Copilot Metrics API and usage dashboards exist only at the org/enterprise level for paid plans (Business/Enterprise). Individual Free licenses report nothing to the company. | Two options: (a) quarterly self-report survey, or (b) upgrade developers to Copilot Business to unlock the Metrics API (per-user acceptance rates, lines accepted, active days). | **None** (survey) or **Full** (if upgraded) |
| **Rovo (Atlassian)** | Adoption and agent usage trends across Jira/Confluence/JSM: active users, feature usage by app, top agents | Atlassian Administration → Insights → **Rovo trends**, CSV export (emailed link). No public API for Rovo usage as of this writing; the audit/admin APIs do not cover it. | **Partial** (monthly manual CSV; semi-automatable later if Atlassian ships an API) |
| **Icertis (ICI)** | Platform reports module (Admin/Legal/Compliance groupings), API call counts, configurable dashboards; AI-feature usage (ExploreAI copilots, clause discovery) via custom reports | ICI REST APIs + Report Admin role to build a custom AI-usage report (SSRS/dynamic views). Engage the Icertis CSM to confirm which AI events are logged. | **Partial → Full** (custom report, then API pull) |
| **pWin.ai** | No public usage API. Per-document reports exist (completeness/attribution) but not admin usage telemetry. | Request a recurring usage report from the vendor (most GovCon SaaS vendors will email a monthly CSV), plus BD-team self-reporting of proposals assisted. | **Manual** (vendor CSV + survey) |

**Two decisions for you before build starts:**

1. **Copilot:** Free plan = permanent blind spot. Either accept survey-only data for
   developers or budget Copilot Business (~$19/user/mo) to get the Metrics API. The upgrade
   often pays for itself in measurement credibility alone if leadership cares about dev metrics.
2. **Claude:** Team plan analytics are a manual export. If Claude usage becomes a headline
   number, the Enterprise plan's Analytics API removes the manual step and adds per-user cost
   attribution. Not required for Phase 1.

---

## 2. KPI definitions

Lock these definitions in writing before any data work, or every meeting becomes a debate
about what "active user" means.

### Adoption KPIs (computed from telemetry/exports)
- **Licensed seats** per tool (from billing/admin consoles)
- **Active users:** WAU and MAU per tool (tool's own definition, documented per source)
- **Activation rate:** MAU ÷ licensed seats (the headline adoption number)
- **Engagement depth:** messages/sessions/actions per active user per week
- **Retention:** % of users active in month M who are also active in M+1
- **Department coverage:** active users by department ÷ department headcount (requires the
  HR roster join, Section 5)

### Efficiency KPIs (modeled, not measured; methodology in Section 3)
- **Estimated hours saved** per tool per month, reported as a **range** (conservative /
  expected), never a single number
- **Hours saved per active user per week**
- **Survey-reported time savings** (the calibration source)

### Financial KPIs
- **Total cost of ownership** per tool: licenses + admin time + training
- **Cost per active user per month** (flags shelfware immediately)
- **Value of hours saved** = hours × fully burdened hourly rate (get the blended rate from
  Finance; use role-specific rates for Copilot/pWin where the population is known)
- **ROI %** = (value of hours saved + hard savings − cost) ÷ cost
- **Payback period** in months

### Tool-specific outcome KPIs (where generic "hours saved" undersells the tool)
- **pWin.ai:** proposals supported, draft turnaround time, and (long-term) win rate on
  AI-assisted vs unassisted bids. For a BD tool, one extra contract win dwarfs hours saved.
- **Icertis:** contract cycle time, % agreements processed with AI clause review
- **Copilot (if upgraded):** suggestion acceptance rate, % of code written with assistance

---

## 3. Methodology: from usage to hours saved to ROI

No vendor tells you hours saved. Anyone claiming otherwise is multiplying usage by a made-up
constant and hiding it. Do the multiplication openly and calibrate it, using three layers:

**Layer 1 — Telemetry (facts):** activity counts per user per tool per day, from Section 1
sources. This is the only layer that is purely factual.

**Layer 2 — Task-time model (assumptions):** map each activity type to minutes saved, with a
conservative and an expected value. Starting points (to be replaced by your own calibration
within two quarters):

| Activity | Conservative | Expected | Basis |
|---|---|---|---|
| ChatGPT/Claude active day (knowledge worker) | 10 min | 25 min | Published enterprise copilot studies cluster at 30–60 min/day for daily users; discount heavily at first |
| Copilot active day (developer) | 15 min | 40 min | GitHub's controlled studies show large per-task speedups; real-world net effect is smaller |
| Rovo search/agent action | 1 min | 3 min | Time-to-find-information studies |
| pWin proposal draft generated | 4 hrs | 16 hrs | BD team's own estimate of first-draft effort displaced; validate with proposal managers |
| Icertis AI clause review per agreement | 15 min | 45 min | Legal team estimate; validate |

**Layer 3 — Survey calibration (validation):** a 5-question quarterly pulse survey to all
licensed users (Microsoft Forms, 2 minutes):

1. Which of these tools did you use in the last month? (list)
2. In a typical week, roughly how much time does AI tooling save you? (0 / <30 min / 30–60 /
   1–3 hrs / 3–8 hrs / 8+ hrs)
3. What task did it help most with? (free text, one line)
4. For Copilot Free users only: roughly how many days/week do you use it?
5. Would losing access to these tools slow you down? (not at all → significantly)

Where survey-reported savings diverge from the Layer 2 model by more than ~30%, adjust the
multipliers and note the change in the dashboard's methodology page. The survey is also the
**only** data source for Copilot Free and a cross-check for pWin.

**ROI calculation (worked example):**

```
Tool: ChatGPT Enterprise, 100 seats @ $60/user/mo = $72,000/yr
MAU = 70, avg active days/user/mo = 12
Expected hours saved = 70 users × 12 days × 25 min = 350 hrs/mo = 4,200 hrs/yr
Conservative          = 70 × 12 × 10 min          = 140 hrs/mo = 1,680 hrs/yr
Blended burdened rate = $85/hr
Value (expected)      = 4,200 × $85 = $357,000/yr  → ROI ≈ 396%
Value (conservative)  = 1,680 × $85 = $142,800/yr  → ROI ≈  98%
Report: "ROI between ~100% and ~400%, methodology attached."
```

The range is the honest answer and survives scrutiny in a way a single number does not.

---

## 4. Architecture

Pragmatic, single-engineer-maintainable. No streaming, no Kafka; this is daily/weekly batch
data measured in megabytes.

```
┌─ SOURCES ────────────────────────────────────────────────────┐
│ API pulls (scheduled):                                       │
│   • OpenAI Compliance/Analytics API   (daily)                │
│   • Claude Code Analytics API         (daily)                │
│   • Icertis custom report API         (weekly, Phase 2)      │
│   • GitHub Copilot Metrics API        (daily, if upgraded)   │
│ CSV drop folder (manual, monthly):                           │
│   • Claude Team analytics export                             │
│   • Rovo trends export                                       │
│   • pWin vendor report                                       │
│   • License/billing exports per tool                         │
│ Survey:                                                      │
│   • MS Forms quarterly pulse → Excel/CSV export              │
│ Reference:                                                   │
│   • HR roster (employee, dept, role, rate band) from         │
│     HRIS/Entra ID export                                     │
└──────────────┬───────────────────────────────────────────────┘
               ▼
  Python connectors (this repo)          one module per source,
  raw payloads archived to /data/raw     idempotent, re-runnable
               ▼
  Warehouse: Postgres (or Azure SQL)     star schema, Section 5
  MVP can start on DuckDB locally        SQLite/DuckDB → Postgres is a config change
               ▼
  SQL metric views (kpi_* views)         one view per KPI, definitions in code
               ▼
  Dashboard: Power BI                    connects to warehouse; you almost certainly
  (fallback: Streamlit app in repo)      already have Power BI in the M365 stack
```

**Stack choices and why:**
- **Python + plain SQL:** every connector is "call API / read CSV → normalize → upsert."
  dbt is optional later; do not start with it.
- **Postgres or Azure SQL:** Astrion is presumably an Azure/M365 shop; Azure SQL keeps it
  inside existing compliance boundaries. DuckDB file for local dev.
- **Power BI for presentation:** leadership already has licenses and trusts it; row-level
  security and scheduled refresh come free. Build the data pipeline here, not the charting.
- **Scheduling:** GitHub Actions cron for API pulls (secrets in repo/environment secrets),
  or an Azure Function/Container App if data must stay inside the tenant.

**Security and privacy (non-negotiable for a GovCon environment):**
- Ingest **metadata only**: user, timestamp, counts, feature names. **Never** prompt or
  conversation content, even though the ChatGPT Compliance API can return it. State this in
  the connector code and the methodology page.
- Treat the OpenAI/Anthropic admin keys as crown-jewel secrets (admin keys can read far more
  than usage counts). Key vault or GitHub environment secrets, never in code.
- Dashboard shows **department-level** numbers by default. Per-user data restricted to the
  tool-admin audience. Announce the measurement program to employees before launch; "we
  count usage events, we never read content" is the message.

---

## 5. Data model

Star schema, four tables to start:

```sql
dim_user (
  user_id        TEXT PRIMARY KEY,   -- canonical: lowercase email
  display_name   TEXT,
  department     TEXT,
  role_family    TEXT,               -- for rate-band mapping
  burdened_rate  NUMERIC,            -- $/hr, from Finance rate bands
  active         BOOLEAN
)

dim_tool (
  tool_id        TEXT PRIMARY KEY,   -- 'chatgpt','claude','copilot','rovo','icertis','pwin'
  vendor         TEXT,
  monthly_cost_per_seat NUMERIC,
  licensed_seats INTEGER,
  data_quality   TEXT                -- 'api' | 'export' | 'survey'  ← shown on dashboard
)

fact_usage_daily (
  date           DATE,
  tool_id        TEXT REFERENCES dim_tool,
  user_id        TEXT REFERENCES dim_user,   -- nullable: some sources are aggregate-only
  metric         TEXT,               -- 'active','messages','agent_actions','drafts',...
  value          NUMERIC,
  source         TEXT,               -- connector name + file/run id (lineage)
  PRIMARY KEY (date, tool_id, user_id, metric, source)
)

fact_survey (
  survey_date    DATE,
  user_id        TEXT,
  tool_id        TEXT,
  weekly_minutes_saved_band TEXT,
  days_per_week  NUMERIC,
  raw_response   JSONB
)
```

Identity resolution: every connector maps its native identity (SSO ID, GitHub handle,
Atlassian account) to email via a `user_mapping` seed table. This is tedious and is also what
makes per-department reporting possible; budget real time for it.

The `data_quality` flag matters: the dashboard must visually distinguish API-measured numbers
from survey-estimated ones, or the first skeptical VP discredits the whole report.

---

## 6. Dashboard spec (Power BI, 4 pages)

1. **Executive overview:** activation rate per tool (gauge vs target), total estimated hours
   saved this quarter (range bar), total AI spend, blended ROI range, 3-month trend.
2. **Adoption:** WAU/MAU trends per tool, department heatmap (tool × dept activation),
   shelfware list (seats with zero usage in 60 days, sorted by cost).
3. **Efficiency & ROI:** per-tool hours-saved ranges, survey vs model comparison chart,
   cost per active user, ROI table with payback period.
4. **Methodology & data quality:** multiplier table with sources, last-refresh date per
   source, coverage gaps (e.g. "Copilot: survey-only"). This page is what makes the other
   three believable.

---

## 7. Phased roadmap

### Phase 0 — Foundations (weeks 1–2, no code)
- [ ] Ratify KPI definitions (Section 2) with whoever owns the AI budget
- [ ] Get admin/API access: OpenAI workspace admin + Compliance API enablement, Anthropic
      Primary Owner + Admin API key, Atlassian org admin, GitHub org owner
- [ ] Ask Icertis CSM and pWin contact: "what usage reporting can you provide monthly?"
- [ ] Decide the Copilot question (survey-only vs upgrade to Business)
- [ ] Get HR roster export and Finance burdened-rate bands
- [ ] Announce the measurement program internally (metadata-only message)

### Phase 1 — MVP on manual exports (weeks 3–6)
- [ ] Repo scaffold: `connectors/`, `data/raw/`, `warehouse/` (schema DDL), `ingest.py`
- [ ] CSV ingesters for: ChatGPT admin analytics export, Claude Team export, Rovo trends
      export, license/seat counts
- [ ] DuckDB/Postgres load + `kpi_adoption` views
- [ ] Power BI page 1–2 (adoption only, no ROI yet)
- **Deliverable:** first real adoption report to leadership. Ship this before modeling ROI;
  adoption numbers alone usually surface a shelfware story worth the whole project.

### Phase 2 — Automation + efficiency model (weeks 7–12)
- [ ] OpenAI Compliance/Analytics API connector on a daily schedule (30-day retention makes
      this the most urgent automation)
- [ ] Claude Code Analytics API connector (if Claude Code in use)
- [ ] Copilot Metrics API connector (if upgraded) or survey question 4 as fallback
- [ ] First quarterly pulse survey + `fact_survey` ingestion
- [ ] Task-time model implemented as a versioned `multipliers.yaml`, hours-saved views
- [ ] Dashboard pages 3–4
- **Deliverable:** full dashboard with hours-saved ranges and ROI, survey-calibrated.

### Phase 3 — Outcomes and hardening (quarter 2)
- [ ] Icertis custom AI-usage report → API pull
- [ ] pWin vendor report ingestion + proposal-outcome join (win rate on assisted bids)
- [ ] Multiplier recalibration from survey wave 2; document changes
- [ ] Retention/churn KPIs, alerting on stalled adoption
- [ ] Evaluate: Claude Enterprise upgrade for the Analytics API; drop manual exports

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Copilot Free is invisible | Decide early: survey or upgrade. Do not present survey data as telemetry. |
| ChatGPT logs expire after 30 days | Phase 2 prioritizes this connector; until then, monthly admin-console exports. |
| "Hours saved" challenged as fiction | Ranges, published multiplier table, survey calibration, methodology page. Never a bare number. |
| Manual CSV exports get skipped | Calendar-driven runbook with a named owner per export; dashboard shows per-source freshness so staleness is visible, not silent. |
| Employee privacy concerns | Metadata-only ingestion, department-level default views, announced program. |
| Identity mapping drift (hires/leavers/renames) | Monthly HR roster refresh is a first-class connector, not a one-off. |

---

## 9. Source references

- [OpenAI Compliance Platform for Enterprise](https://help.openai.com/en/articles/9261474-compliance-apis-for-enterprise-customers) and [Compliance API vs User Analytics](https://help.openai.com/en/articles/11327494-compliance-api-vs-user-analytics-in-chatgpt-enterpriseedu), [Workspace analytics](https://help.openai.com/en/articles/10875114-user-analytics-for-chatgpt-enterprise-and-edu)
- [Anthropic: usage analytics for Team/Enterprise](https://support.claude.com/en/articles/12883420-view-usage-analytics-for-team-and-enterprise-plans), [Claude Code Analytics API](https://platform.claude.com/docs/en/manage-claude/claude-code-analytics-api), [Enterprise Analytics API](https://support.claude.com/en/articles/13703965-claude-enterprise-analytics-api-reference-guide)
- [GitHub Copilot metrics API](https://docs.github.com/en/rest/copilot/copilot-metrics), [Copilot usage metrics concepts](https://docs.github.com/en/copilot/concepts/copilot-usage-metrics/copilot-metrics)
- [Atlassian: Rovo AI activity insights](https://support.atlassian.com/organization-administration/docs/gain-insights-into-rovo-ai-activity/), [Platform usage dashboard announcement](https://community.atlassian.com/forums/Community-Announcements-articles/Org-admins-Gain-insights-into-how-your-org-is-using-Rovo-Rovo/ba-p/3146791)
- [Icertis API capabilities](https://iciwikiapac.icertis.com/ICIHelp8.2/index.php?title=API_Capabilities), [ICI Reports](https://ici-us-wiki01.icertis.com/ICIHelp8.2/index.php?title=Reports)
