-- Star schema for AI usage metrics (see PLAN.md section 5).

CREATE TABLE IF NOT EXISTS dim_user (
    user_id       TEXT PRIMARY KEY,   -- canonical: lowercase email
    display_name  TEXT,
    department    TEXT,
    role_family   TEXT,
    burdened_rate DOUBLE,             -- $/hr fully burdened; NULL = use org default
    active        BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_tool (
    tool_id               TEXT PRIMARY KEY,
    display_name          TEXT,
    vendor                TEXT,
    monthly_cost_per_seat DOUBLE DEFAULT 0,
    monthly_flat_cost     DOUBLE DEFAULT 0,
    licensed_seats        INTEGER DEFAULT 0,
    data_quality          TEXT CHECK (data_quality IN ('api', 'export', 'vendor', 'survey'))
);

-- Maps tool-native identities (GitHub handle, Atlassian account id, ...) to
-- the canonical email user_id.
CREATE TABLE IF NOT EXISTS user_mapping (
    source    TEXT,
    native_id TEXT,
    user_id   TEXT,
    PRIMARY KEY (source, native_id)
);

-- One row per (day, tool, user, metric, source). user_id = '' means an
-- org-level aggregate (sources that don't expose per-user data).
CREATE TABLE IF NOT EXISTS fact_usage_daily (
    date        DATE NOT NULL,
    tool_id     TEXT NOT NULL,
    user_id     TEXT NOT NULL DEFAULT '',
    metric      TEXT NOT NULL,
    value       DOUBLE NOT NULL,
    source      TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (date, tool_id, user_id, metric, source)
);

-- Quarterly pulse survey responses (calibration layer; never mixed into
-- telemetry facts).
CREATE TABLE IF NOT EXISTS fact_survey (
    survey_date               DATE NOT NULL,
    user_id                   TEXT NOT NULL,
    tools_used                TEXT,    -- comma-separated tool_ids
    weekly_minutes_saved_band TEXT,
    weekly_minutes_saved_mid  DOUBLE,  -- band midpoint, minutes/week
    copilot_days_per_week     DOUBLE,
    dependence                TEXT,
    top_task                  TEXT,
    PRIMARY KEY (survey_date, user_id)
);

-- Task-time model (minutes saved per unit of metric), versioned for audit.
CREATE TABLE IF NOT EXISTS multiplier (
    tool_id                    TEXT NOT NULL,
    metric                     TEXT NOT NULL,
    unit                       TEXT,
    minutes_saved_conservative DOUBLE NOT NULL,
    minutes_saved_expected     DOUBLE NOT NULL,
    basis                      TEXT,
    version                    TEXT NOT NULL,
    PRIMARY KEY (tool_id, metric, version)
);

CREATE TABLE IF NOT EXISTS config_kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS ingest_log (
    source      TEXT,
    file_or_run TEXT,
    rows_loaded INTEGER,
    min_date    DATE,
    max_date    DATE,
    ingested_at TIMESTAMP DEFAULT current_timestamp
);
