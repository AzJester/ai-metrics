-- KPI views. One view per KPI so the definition lives in code, not in a BI
-- formula. All views read v_fact_dedup, which collapses overlapping sources
-- (e.g. a manual export and an API pull covering the same days) by taking
-- the max value per (date, tool, user, metric), so double ingestion never
-- double counts.

CREATE OR REPLACE VIEW v_fact_dedup AS
SELECT date, tool_id, user_id, metric, MAX(value) AS value
FROM fact_usage_daily
GROUP BY 1, 2, 3, 4;

-- Latest multiplier version only (versions sort as YYYY-MM strings).
CREATE OR REPLACE VIEW v_multiplier_current AS
SELECT *
FROM multiplier
WHERE version = (SELECT MAX(version) FROM multiplier);

-- Per-user monthly activity rollup. 'active' rows are daily flags (value 1);
-- 'active_days' rows come from monthly-grain exports (value = day count).
CREATE OR REPLACE VIEW v_user_activity_monthly AS
SELECT
    date_trunc('month', date)::DATE AS month,
    tool_id,
    user_id,
    SUM(CASE WHEN metric = 'active' AND value > 0 THEN 1
             WHEN metric = 'active_days' THEN value
             ELSE 0 END) AS active_days,
    SUM(CASE WHEN metric = 'messages' THEN value END) AS messages
FROM v_fact_dedup
WHERE user_id <> ''
GROUP BY 1, 2, 3;

-- Adoption: MAU and activation rate per tool per month. Prefers user-level
-- data; falls back to org-level reported active users (note: the fallback is
-- the peak reported daily value, a lower bound on true MAU, unless the
-- export carries month-grain values).
CREATE OR REPLACE VIEW kpi_adoption_monthly AS
WITH user_level AS (
    SELECT date_trunc('month', date)::DATE AS month, tool_id,
           COUNT(DISTINCT user_id) AS mau
    FROM v_fact_dedup
    WHERE user_id <> '' AND metric IN ('active', 'active_days') AND value > 0
    GROUP BY 1, 2
),
org_level AS (
    SELECT date_trunc('month', date)::DATE AS month, tool_id,
           MAX(CASE WHEN metric = 'active_users' THEN value END) AS mau_reported
    FROM v_fact_dedup
    WHERE user_id = ''
    GROUP BY 1, 2
),
months AS (
    SELECT month, tool_id FROM user_level
    UNION
    SELECT month, tool_id FROM org_level
)
SELECT
    m.month,
    m.tool_id,
    t.display_name,
    COALESCE(u.mau, o.mau_reported) AS mau,
    t.licensed_seats,
    CASE WHEN t.licensed_seats > 0
         THEN ROUND(COALESCE(u.mau, o.mau_reported) / t.licensed_seats::DOUBLE, 3)
    END AS activation_rate,
    CASE WHEN t.licensed_seats > 0
         THEN GREATEST(t.licensed_seats - COALESCE(u.mau, o.mau_reported), 0)
    END AS seats_inactive,
    t.data_quality
FROM months m
JOIN dim_tool t ON t.tool_id = m.tool_id
LEFT JOIN user_level u ON u.month = m.month AND u.tool_id = m.tool_id
LEFT JOIN org_level o ON o.month = m.month AND o.tool_id = m.tool_id;

CREATE OR REPLACE VIEW kpi_adoption_weekly AS
SELECT
    date_trunc('week', date)::DATE AS week,
    tool_id,
    COUNT(DISTINCT user_id) AS wau
FROM v_fact_dedup
WHERE user_id <> '' AND metric IN ('active', 'active_days') AND value > 0
GROUP BY 1, 2;

CREATE OR REPLACE VIEW kpi_engagement_monthly AS
SELECT
    month,
    tool_id,
    COUNT(*) AS active_users,
    ROUND(AVG(active_days), 1) AS avg_active_days,
    ROUND(SUM(messages) / NULLIF(COUNT(*), 0), 1) AS messages_per_active_user
FROM v_user_activity_monthly
WHERE active_days > 0
GROUP BY 1, 2;

CREATE OR REPLACE VIEW v_department_monthly AS
SELECT
    a.month,
    a.tool_id,
    COALESCE(u.department, '(unmapped)') AS department,
    COUNT(DISTINCT a.user_id) AS active_users
FROM v_user_activity_monthly a
LEFT JOIN dim_user u ON u.user_id = a.user_id
WHERE a.active_days > 0
GROUP BY 1, 2, 3;

-- Retention: share of a month's active users who are active again the
-- following month.
CREATE OR REPLACE VIEW kpi_retention_monthly AS
WITH actives AS (
    SELECT DISTINCT month, tool_id, user_id
    FROM v_user_activity_monthly
    WHERE active_days > 0
)
SELECT
    a.month,
    a.tool_id,
    COUNT(*) AS active_users,
    COUNT(n.user_id) AS retained_next_month,
    ROUND(COUNT(n.user_id) / NULLIF(COUNT(*), 0)::DOUBLE, 3) AS retention_rate
FROM actives a
LEFT JOIN actives n
    ON n.tool_id = a.tool_id
    AND n.user_id = a.user_id
    AND n.month = (a.month + INTERVAL 1 MONTH)::DATE
GROUP BY 1, 2;

-- Hours saved: telemetry x task-time multipliers, as a conservative/expected
-- range. Per tool-month, user-level rows win over org-level rows so a tool
-- reporting both is not double counted.
CREATE OR REPLACE VIEW kpi_hours_saved_monthly AS
WITH joined AS (
    SELECT
        date_trunc('month', f.date)::DATE AS month,
        f.tool_id,
        f.user_id <> '' AS user_level,
        f.value * m.minutes_saved_conservative AS minutes_c,
        f.value * m.minutes_saved_expected AS minutes_e
    FROM v_fact_dedup f
    JOIN v_multiplier_current m
        ON m.tool_id = f.tool_id AND m.metric = f.metric
),
agg AS (
    SELECT month, tool_id, user_level,
           SUM(minutes_c) AS minutes_c,
           SUM(minutes_e) AS minutes_e
    FROM joined
    GROUP BY 1, 2, 3
)
SELECT
    month,
    tool_id,
    ROUND(COALESCE(MAX(CASE WHEN user_level THEN minutes_c END),
                   MAX(CASE WHEN NOT user_level THEN minutes_c END)) / 60.0, 1)
        AS hours_saved_conservative,
    ROUND(COALESCE(MAX(CASE WHEN user_level THEN minutes_e END),
                   MAX(CASE WHEN NOT user_level THEN minutes_e END)) / 60.0, 1)
        AS hours_saved_expected
FROM agg
GROUP BY 1, 2;

-- ROI: value of hours saved vs monthly cost, plus cost per active user.
CREATE OR REPLACE VIEW kpi_roi_monthly AS
WITH rate AS (
    SELECT CAST(value AS DOUBLE) AS hourly_rate
    FROM config_kv WHERE key = 'default_burdened_rate'
),
cost AS (
    SELECT tool_id,
           licensed_seats * monthly_cost_per_seat + monthly_flat_cost AS monthly_cost_usd
    FROM dim_tool
)
SELECT
    h.month,
    h.tool_id,
    t.display_name,
    h.hours_saved_conservative,
    h.hours_saved_expected,
    ROUND(h.hours_saved_conservative * r.hourly_rate, 0) AS value_conservative_usd,
    ROUND(h.hours_saved_expected * r.hourly_rate, 0) AS value_expected_usd,
    ROUND(c.monthly_cost_usd, 0) AS monthly_cost_usd,
    CASE WHEN c.monthly_cost_usd > 0 THEN
        ROUND((h.hours_saved_conservative * r.hourly_rate - c.monthly_cost_usd)
              / c.monthly_cost_usd, 2)
    END AS roi_conservative,
    CASE WHEN c.monthly_cost_usd > 0 THEN
        ROUND((h.hours_saved_expected * r.hourly_rate - c.monthly_cost_usd)
              / c.monthly_cost_usd, 2)
    END AS roi_expected,
    a.mau,
    CASE WHEN a.mau > 0 THEN ROUND(c.monthly_cost_usd / a.mau, 2) END
        AS cost_per_active_user_usd,
    t.data_quality
FROM kpi_hours_saved_monthly h
JOIN dim_tool t ON t.tool_id = h.tool_id
JOIN cost c ON c.tool_id = h.tool_id
LEFT JOIN kpi_adoption_monthly a ON a.month = h.month AND a.tool_id = h.tool_id
CROSS JOIN rate r;

-- Survey calibration: what respondents say vs what the model implies.
CREATE OR REPLACE VIEW kpi_survey_summary AS
SELECT
    date_trunc('month', survey_date)::DATE AS month,
    COUNT(*) AS responses,
    ROUND(AVG(weekly_minutes_saved_mid), 1) AS avg_weekly_minutes_reported,
    ROUND(SUM(weekly_minutes_saved_mid) * 4.33 / 60.0, 1) AS implied_monthly_hours_respondents
FROM fact_survey
GROUP BY 1;

CREATE OR REPLACE VIEW v_survey_tool_mentions AS
WITH exploded AS (
    SELECT
        date_trunc('month', survey_date)::DATE AS month,
        unnest(string_split(tools_used, ',')) AS tool_raw
    FROM fact_survey
    WHERE tools_used IS NOT NULL AND tools_used <> ''
)
SELECT month, trim(tool_raw) AS tool_id, COUNT(*) AS mentions
FROM exploded
GROUP BY 1, 2;

-- Per-source freshness, so stale manual exports are visible, not silent.
CREATE OR REPLACE VIEW v_source_freshness AS
SELECT
    source,
    MAX(max_date) AS latest_data_date,
    MAX(ingested_at) AS last_ingested_at,
    SUM(rows_loaded) AS total_rows_loaded
FROM ingest_log
GROUP BY source;
