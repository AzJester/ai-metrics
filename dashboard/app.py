"""Streamlit dashboard over the DuckDB warehouse (read-only).

Run with: ai-metrics dashboard
Pages mirror PLAN.md section 6. On hosted deployments (Streamlit Community
Cloud) the warehouse is rebuilt on boot from CSVs committed to data/public/,
falling back to generated demo data. The KPI definitions stay in the SQL
views either way.
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from ai_metrics.bootstrap import ensure_warehouse

REPO_ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="AI Usage Metrics", layout="wide")

try:
    DB_PATH, DB_MODE = ensure_warehouse(REPO_ROOT)
except Exception as e:
    st.error(f"Could not initialize the warehouse: {e}")
    st.stop()

if DB_MODE == "sample":
    st.sidebar.warning(
        "Showing generated demo data. Commit real exports to `data/public/` "
        "to replace it."
    )


@st.cache_resource
def get_con():
    return duckdb.connect(str(DB_PATH), read_only=True)


def q(sql: str, params=None) -> pd.DataFrame:
    return get_con().execute(sql, params or []).df()


page = st.sidebar.radio(
    "Page", ["Executive overview", "Adoption", "Efficiency & ROI", "Methodology & data quality"]
)
months = q("SELECT DISTINCT month FROM kpi_adoption_monthly ORDER BY month DESC")["month"].tolist()
if not months:
    st.warning("No usage data yet. Run `ai-metrics ingest`.")
    st.stop()
month = st.sidebar.selectbox("Month", months, index=0)

if page == "Executive overview":
    st.title("AI tools: executive overview")
    roi = q("SELECT * FROM kpi_roi_monthly WHERE month = ?", [month])
    adoption = q("SELECT * FROM kpi_adoption_monthly WHERE month = ?", [month])

    c1, c2, c3, c4 = st.columns(4)
    hrs_c = roi["hours_saved_conservative"].sum()
    hrs_e = roi["hours_saved_expected"].sum()
    cost = roi["monthly_cost_usd"].sum()
    val_c, val_e = roi["value_conservative_usd"].sum(), roi["value_expected_usd"].sum()
    c1.metric("Est. hours saved (month)", f"{hrs_c:,.0f} – {hrs_e:,.0f}")
    c2.metric("Value of hours saved", f"${val_c:,.0f} – ${val_e:,.0f}")
    c3.metric("Monthly AI spend", f"${cost:,.0f}")
    if cost > 0:
        c4.metric("Blended ROI", f"{(val_c - cost) / cost:,.0%} – {(val_e - cost) / cost:,.0%}")
    else:
        c4.metric("Blended ROI", "n/a (no cost data)")
    st.caption("Ranges are conservative–expected per the task-time model; "
               "see Methodology page.")

    st.subheader("Monthly active users by tool")
    trend = q("SELECT month, display_name AS tool, mau FROM kpi_adoption_monthly ORDER BY month")
    st.altair_chart(
        alt.Chart(trend).mark_line(point=True).encode(
            x="month:T", y="mau:Q", color="tool:N",
            tooltip=["month:T", "tool:N", "mau:Q"],
        ),
        width="stretch",
    )

    st.subheader("Activation rate (MAU / licensed seats)")
    st.dataframe(
        adoption[["display_name", "mau", "licensed_seats", "activation_rate",
                  "seats_inactive", "data_quality"]],
        hide_index=True, width="stretch",
    )

elif page == "Adoption":
    st.title("Adoption")
    st.subheader("Weekly active users")
    wau = q("SELECT week, tool_id, wau FROM kpi_adoption_weekly ORDER BY week")
    st.altair_chart(
        alt.Chart(wau).mark_line(point=True).encode(
            x="week:T", y="wau:Q", color="tool_id:N",
            tooltip=["week:T", "tool_id:N", "wau:Q"],
        ),
        width="stretch",
    )

    st.subheader(f"Department × tool active users ({month})")
    dept = q("SELECT * FROM v_department_monthly WHERE month = ?", [month])
    if dept.empty:
        st.info("No user-level data for this month (org-level-only sources don't "
                "appear here).")
    else:
        st.altair_chart(
            alt.Chart(dept).mark_rect().encode(
                x="tool_id:N", y="department:N",
                color=alt.Color("active_users:Q", scale=alt.Scale(scheme="blues")),
                tooltip=["tool_id:N", "department:N", "active_users:Q"],
            ),
            width="stretch",
        )

    st.subheader("Engagement")
    st.dataframe(q("SELECT * FROM kpi_engagement_monthly WHERE month = ?", [month]),
                 hide_index=True, width="stretch")

    st.subheader("Month-over-month retention")
    st.dataframe(q("SELECT * FROM kpi_retention_monthly ORDER BY month DESC, tool_id"),
                 hide_index=True, width="stretch")

elif page == "Efficiency & ROI":
    st.title("Efficiency & ROI")
    hrs = q(
        """
        SELECT h.month, t.display_name AS tool,
               h.hours_saved_conservative, h.hours_saved_expected
        FROM kpi_hours_saved_monthly h JOIN dim_tool t USING (tool_id)
        WHERE h.month = ?
        """,
        [month],
    )
    folded = hrs.melt(
        id_vars=["month", "tool"],
        value_vars=["hours_saved_conservative", "hours_saved_expected"],
        var_name="estimate", value_name="hours",
    )
    folded["estimate"] = folded["estimate"].str.replace("hours_saved_", "")
    st.subheader(f"Estimated hours saved ({month})")
    st.altair_chart(
        alt.Chart(folded).mark_bar().encode(
            x="tool:N", xOffset="estimate:N", y="hours:Q", color="estimate:N",
            tooltip=["tool:N", "estimate:N", "hours:Q"],
        ),
        width="stretch",
    )

    st.subheader("ROI by tool")
    st.dataframe(
        q(
            """
            SELECT display_name AS tool, hours_saved_conservative, hours_saved_expected,
                   value_conservative_usd, value_expected_usd, monthly_cost_usd,
                   roi_conservative, roi_expected, mau, cost_per_active_user_usd, data_quality
            FROM kpi_roi_monthly WHERE month = ? ORDER BY value_expected_usd DESC
            """,
            [month],
        ),
        hide_index=True, width="stretch",
    )
    st.caption("ROI is null where cost is zero/unknown; fill in contract costs "
               "in config/tools.yaml.")

    st.subheader("Survey calibration")
    st.dataframe(q("SELECT * FROM kpi_survey_summary ORDER BY month"),
                 hide_index=True, width="stretch")
    mentions = q("SELECT * FROM v_survey_tool_mentions ORDER BY month, mentions DESC")
    if not mentions.empty:
        st.dataframe(mentions, hide_index=True, width="stretch")

else:
    st.title("Methodology & data quality")
    st.markdown(
        """
**How these numbers are produced** (full detail in `PLAN.md`):

1. **Telemetry** (facts): activity counts per user/tool/day from vendor APIs
   and admin-console exports. Metadata only; conversation content is never
   ingested.
2. **Task-time model** (assumptions): minutes saved per unit of activity,
   versioned in `config/multipliers.yaml` and shown below.
3. **Survey calibration** (validation): a quarterly pulse survey; where it
   diverges from the model by more than ~30%, the multipliers get revised.

Hours saved and ROI are always shown as a **conservative–expected range**.
"""
    )
    st.subheader("Current task-time multipliers")
    st.dataframe(q("SELECT * FROM v_multiplier_current ORDER BY tool_id, metric"),
                 hide_index=True, width="stretch")

    st.subheader("How each tool is measured")
    st.dataframe(
        q("SELECT tool_id, display_name, vendor, data_quality, licensed_seats FROM dim_tool"),
        hide_index=True, width="stretch",
    )

    st.subheader("Source freshness")
    fresh = q("SELECT * FROM v_source_freshness ORDER BY source")
    if fresh.empty:
        st.info("Nothing ingested yet.")
    else:
        st.dataframe(fresh, hide_index=True, width="stretch")
        stale = fresh[pd.to_datetime(fresh["last_ingested_at"])
                      < pd.Timestamp.now() - pd.Timedelta(days=35)]
        if not stale.empty:
            st.warning("Stale sources (no ingest in 35+ days): "
                       + ", ".join(stale["source"].tolist()))
