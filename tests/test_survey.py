import pandas as pd

from ai_metrics.ingest import survey


def test_band_normalization():
    assert survey._norm_band("1 - 3 hrs") == "1-3 hrs"
    assert survey.BAND_MINUTES[survey._norm_band("30-60 min")] == 45.0
    assert survey.BAND_MINUTES[survey._norm_band("8+ hrs")] == 600.0


def test_tool_name_mapping():
    assert survey._norm_tools("ChatGPT; GitHub Copilot") == "chatgpt,copilot"
    assert survey._norm_tools("pWin.ai, Rovo") == "pwin,rovo"


def test_survey_ingest(con):
    df = pd.DataFrame(
        {
            "timestamp": ["2026-05-15", "2026-05-15"],
            "email": ["A@X.com", "b@x.com"],
            "tools_used": ["ChatGPT; Claude", "Rovo"],
            "weekly_time_saved_band": ["1-3 hrs", "<30 min"],
            "top_task": ["drafting", "search"],
            "copilot_days_per_week": [0, 3],
            "dependence": ["moderately", "slightly"],
        }
    )
    n = survey.ingest(con, df, "survey_test.csv")
    assert n == 2
    mid = con.execute(
        "SELECT weekly_minutes_saved_mid FROM fact_survey WHERE user_id = 'a@x.com'"
    ).fetchone()[0]
    assert mid == 120.0
    summary = con.execute("SELECT responses FROM kpi_survey_summary").fetchone()
    assert summary[0] == 2
    mentions = con.execute(
        "SELECT tool_id, mentions FROM v_survey_tool_mentions ORDER BY tool_id"
    ).fetchall()
    assert ("chatgpt", 1) in mentions and ("rovo", 1) in mentions
