-- PLATFORM GOD Registry Schema
-- SQLite database for deterministic runs, auditability, replay, governance,
-- prompt versioning, findings, artifacts, and agent execution records.

-- ============================================================================
-- REQUIRED SQLITE SETTINGS
-- ============================================================================
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- ============================================================================
-- TABLE: projects
-- Registry of all projects being tracked and governed.
-- ============================================================================
CREATE TABLE projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT,
    repository_url  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    metadata        TEXT,                    -- JSON metadata
    governance_status TEXT DEFAULT 'active' CHECK(governance_status IN ('active', 'suspended', 'archived', 'deprecated'))
);

CREATE INDEX idx_projects_name ON projects(name);
CREATE INDEX idx_projects_is_active ON projects(is_active);
CREATE INDEX idx_projects_governance_status ON projects(governance_status);

-- ============================================================================
-- TABLE: tags
-- Hierarchical and categorical tags for organizing projects and findings.
-- ============================================================================
CREATE TABLE tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    color           TEXT,
    description     TEXT,
    parent_id       INTEGER REFERENCES tags(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    metadata        TEXT                     -- JSON metadata
);

CREATE INDEX idx_tags_name ON tags(name);
CREATE INDEX idx_tags_parent_id ON tags(parent_id);

-- ============================================================================
-- TABLE: project_tags
-- Many-to-many relationship between projects and tags.
-- ============================================================================
CREATE TABLE project_tags (
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    tag_id          INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    applied_at      TEXT NOT NULL DEFAULT (datetime('now')),
    applied_by      TEXT,
    PRIMARY KEY (project_id, tag_id)
);

CREATE INDEX idx_project_tags_tag_id ON project_tags(tag_id);

-- ============================================================================
-- TABLE: project_relationships
-- Relationships and dependencies between projects.
-- ============================================================================
CREATE TABLE project_relationships (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    target_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL CHECK(relationship_type IN ('depends_on', 'implements', 'extends', 'supersedes', 'incompatible_with', 'related_to')),
    description     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK(source_id != target_id)
);

CREATE INDEX idx_project_relationships_source ON project_relationships(source_id);
CREATE INDEX idx_project_relationships_target ON project_relationships(target_id);
CREATE INDEX idx_project_relationships_type ON project_relationships(relationship_type);

-- ============================================================================
-- TABLE: agents
-- Registry of all agents available for execution.
-- ============================================================================
CREATE TABLE agents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    type            TEXT NOT NULL,
    version         TEXT NOT NULL,
    description     TEXT,
    entrypoint      TEXT NOT NULL,
    config_schema   TEXT,                    -- JSON schema for agent configuration
    capabilities    TEXT,                    -- JSON array of capabilities
    constraints     TEXT,                    -- JSON array of constraints
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    metadata        TEXT,
    CHECK(type IN ('analysis', 'remediation', 'governance', 'testing', 'monitoring', 'custom'))
);

CREATE INDEX idx_agents_name ON agents(name);
CREATE INDEX idx_agents_type ON agents(type);
CREATE INDEX idx_agents_is_active ON agents(is_active);

-- ============================================================================
-- TABLE: agent_output_schemas
-- Expected output schemas for agent runs (for validation).
-- ============================================================================
CREATE TABLE agent_output_schemas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    schema_name     TEXT NOT NULL,
    version         TEXT NOT NULL,
    schema_json     TEXT NOT NULL,           -- JSON schema definition
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    is_current      INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
    UNIQUE(agent_id, schema_name, version)
);

CREATE INDEX idx_agent_output_schemas_agent_id ON agent_output_schemas(agent_id);
CREATE INDEX idx_agent_output_schemas_schema_name ON agent_output_schemas(schema_name);
CREATE INDEX idx_agent_output_schemas_is_current ON agent_output_schemas(is_current);

-- ============================================================================
-- TABLE: runs
-- Top-level execution runs (e.g., governance pass, audit).
-- ============================================================================
CREATE TABLE runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL UNIQUE,    -- UUID for external reference
    run_type        TEXT NOT NULL CHECK(run_type IN ('governance', 'audit', 'analysis', 'remediation', 'baseline', 'custom')),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'replaying')),
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT,
    initiated_by    TEXT,
    parameters      TEXT,                    -- JSON run parameters
    result_summary  TEXT,                    -- JSON summary of results
    parent_run_id   TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
    is_replay       INTEGER NOT NULL DEFAULT 0 CHECK(is_replay IN (0, 1)),
    original_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
    error_message   TEXT
);

CREATE INDEX idx_runs_run_id ON runs(run_id);
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_type ON runs(run_type);
CREATE INDEX idx_runs_started_at ON runs(started_at);
CREATE INDEX idx_runs_parent_run_id ON runs(parent_run_id);

-- ============================================================================
-- TABLE: run_targets
-- Projects or scopes targeted by a run.
-- ============================================================================
CREATE TABLE run_targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    target_path     TEXT,                    -- Path within project (null = whole project)
    scope           TEXT NOT NULL DEFAULT 'full' CHECK(scope IN ('full', 'path', 'module', 'function')),
    included_at     TEXT NOT NULL DEFAULT (datetime('now')),
    priority        INTEGER DEFAULT 0
);

CREATE INDEX idx_run_targets_run_id ON run_targets(run_id);
CREATE INDEX idx_run_targets_project_id ON run_targets(project_id);

-- ============================================================================
-- TABLE: agent_runs
-- Individual agent executions within a run.
-- ============================================================================
CREATE TABLE agent_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_run_id    TEXT NOT NULL UNIQUE,    -- UUID for external reference
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    agent_id        INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    target_id       INTEGER REFERENCES run_targets(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT,
    input_hash      TEXT,                    -- Hash of inputs for replay verification
    input_data      TEXT,                    -- JSON input data
    output_data     TEXT,                    -- JSON output data
    output_schema_id INTEGER REFERENCES agent_output_schemas(id) ON DELETE SET NULL,
    validation_passed INTEGER,              -- NULL if not validated, 0/1 if validated
    error_message   TEXT,
    execution_time_ms INTEGER,
    token_usage     TEXT,                    -- JSON token usage stats
    is_deterministic INTEGER NOT NULL DEFAULT 1 CHECK(is_deterministic IN (0, 1)),
    replay_count    INTEGER NOT NULL DEFAULT 0,
    metadata        TEXT
);

CREATE INDEX idx_agent_runs_agent_run_id ON agent_runs(agent_run_id);
CREATE INDEX idx_agent_runs_run_id ON agent_runs(run_id);
CREATE INDEX idx_agent_runs_agent_id ON agent_runs(agent_id);
CREATE INDEX idx_agent_runs_status ON agent_runs(status);
CREATE INDEX idx_agent_runs_input_hash ON agent_runs(input_hash);

-- ============================================================================
-- TABLE: findings
-- Findings generated during agent runs (issues, vulnerabilities, observations).
-- ============================================================================
CREATE TABLE findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id      TEXT NOT NULL UNIQUE,    -- UUID for external reference
    agent_run_id    TEXT NOT NULL REFERENCES agent_runs(agent_run_id) ON DELETE CASCADE,
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    severity        TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info', 'none')),
    category        TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    location_path   TEXT,
    location_line   INTEGER,
    location_end_line INTEGER,
    rule_id         TEXT,
    cwe_id          TEXT,
    confidence      TEXT CHECK(confidence IN ('certain', 'high', 'medium', 'low', 'unknown')),
    status          TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'acknowledged', 'false_positive', 'resolved', 'mitigated', 'wontfix')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at     TEXT,
    resolved_by     TEXT,
    mitigation      TEXT,
    metadata        TEXT,
    is_suppressed   INTEGER NOT NULL DEFAULT 0 CHECK(is_suppressed IN (0, 1)),
    suppress_reason TEXT
);

CREATE INDEX idx_findings_finding_id ON findings(finding_id);
CREATE INDEX idx_findings_agent_run_id ON findings(agent_run_id);
CREATE INDEX idx_findings_project_id ON findings(project_id);
CREATE INDEX idx_findings_severity ON findings(severity);
CREATE INDEX idx_findings_status ON findings(status);
CREATE INDEX idx_findings_category ON findings(category);
CREATE INDEX idx_findings_location_path ON findings(location_path);

-- ============================================================================
-- TABLE: artifacts
-- Generated artifacts (reports, patches, documentation, etc.).
-- ============================================================================
CREATE TABLE artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id     TEXT NOT NULL UNIQUE,    -- UUID for external reference
    agent_run_id    TEXT REFERENCES agent_runs(agent_run_id) ON DELETE SET NULL,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    artifact_type   TEXT NOT NULL CHECK(artifact_type IN ('report', 'patch', 'documentation', 'test', 'config', 'binary', 'scan_result', 'custom')),
    title           TEXT NOT NULL,
    description     TEXT,
    file_path       TEXT,                    -- Local filesystem path
    storage_path    TEXT,                    -- Storage location (e.g., S3 key)
    content_hash    TEXT,                    -- SHA256 hash
    size_bytes      INTEGER,
    mime_type       TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    metadata        TEXT,                    -- JSON metadata
    is_persistent   INTEGER NOT NULL DEFAULT 1 CHECK(is_persistent IN (0, 1))
);

CREATE INDEX idx_artifacts_artifact_id ON artifacts(artifact_id);
CREATE INDEX idx_artifacts_agent_run_id ON artifacts(agent_run_id);
CREATE INDEX idx_artifacts_run_id ON artifacts(run_id);
CREATE INDEX idx_artifacts_project_id ON artifacts(project_id);
CREATE INDEX idx_artifacts_type ON artifacts(artifact_type);
CREATE INDEX idx_artifacts_content_hash ON artifacts(content_hash);

-- ============================================================================
-- TABLE: decisions
-- Governance decisions made during runs.
-- ============================================================================
CREATE TABLE decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id     TEXT NOT NULL UNIQUE,    -- UUID for external reference
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    decision_type   TEXT NOT NULL CHECK(decision_type IN ('approval', 'rejection', 'waiver', 'escalation', 'policy_exception', 'remediation_required', 'no_action')),
    subject_type    TEXT NOT NULL,           -- e.g., 'finding', 'artifact', 'agent_run'
    subject_id      TEXT NOT NULL,           -- ID of the subject
    rationale       TEXT NOT NULL,
    decision_maker TEXT,                    -- System, user, or role
    decision_date   TEXT NOT NULL DEFAULT (datetime('now')),
    effective_until TEXT,                    -- NULL = permanent
    conditions      TEXT,                    -- JSON conditions
    requirements    TEXT,                    -- JSON requirements
    is_appealable   INTEGER NOT NULL DEFAULT 1 CHECK(is_appealable IN (0, 1)),
    parent_decision_id TEXT REFERENCES decisions(decision_id) ON DELETE SET NULL,
    metadata        TEXT
);

CREATE INDEX idx_decisions_decision_id ON decisions(decision_id);
CREATE INDEX idx_decisions_run_id ON decisions(run_id);
CREATE INDEX idx_decisions_project_id ON decisions(project_id);
CREATE INDEX idx_decisions_type ON decisions(decision_type);
CREATE INDEX idx_decisions_subject ON decisions(decision_type, subject_id);
CREATE INDEX idx_decisions_parent_id ON decisions(parent_decision_id);

-- ============================================================================
-- TABLE: prompt_versions
-- Version tracking for prompts used in agent executions.
-- ============================================================================
CREATE TABLE prompt_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id       TEXT NOT NULL,           -- Logical prompt identifier
    version         TEXT NOT NULL,
    name            TEXT NOT NULL,
    content         TEXT NOT NULL,           -- Full prompt text
    template_vars   TEXT,                    -- JSON array of variable names
    hash            TEXT NOT NULL,           -- SHA256 of content
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    deprecated_at   TEXT,
    deprecation_reason TEXT,
    parent_version_id INTEGER REFERENCES prompt_versions(id) ON DELETE SET NULL,
    metadata        TEXT,
    UNIQUE(prompt_id, version)
);

CREATE INDEX idx_prompt_versions_prompt_id ON prompt_versions(prompt_id);
CREATE INDEX idx_prompt_versions_hash ON prompt_versions(hash);
CREATE INDEX idx_prompt_versions_is_active ON prompt_versions(is_active);
CREATE INDEX idx_prompt_versions_parent_id ON prompt_versions(parent_version_id);

-- ============================================================================
-- TABLE: baselines
-- Baseline snapshots for comparison and regression detection.
-- ============================================================================
CREATE TABLE baselines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    baseline_id     TEXT NOT NULL UNIQUE,    -- UUID for external reference
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    baseline_type   TEXT NOT NULL CHECK(baseline_type IN ('security', 'performance', 'compliance', 'quality', 'custom')),
    snapshot_data   TEXT NOT NULL,           -- JSON snapshot data
    snapshot_hash   TEXT NOT NULL,
    captured_at     TEXT NOT NULL DEFAULT (datetime('now')),
    captured_by_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
    is_current      INTEGER NOT NULL DEFAULT 0 CHECK(is_current IN (0, 1)),
    valid_from      TEXT NOT NULL DEFAULT (datetime('now')),
    valid_until     TEXT,                    -- NULL = indefinite
    metadata        TEXT
);

CREATE INDEX idx_baselines_baseline_id ON baselines(baseline_id);
CREATE INDEX idx_baselines_project_id ON baselines(project_id);
CREATE INDEX idx_baselines_type ON baselines(baseline_type);
CREATE INDEX idx_baselines_is_current ON baselines(is_current);
CREATE INDEX idx_baselines_snapshot_hash ON baselines(snapshot_hash);

-- ============================================================================
-- TABLE: notifications
-- Notification log for alerts and events.
-- ============================================================================
CREATE TABLE notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id TEXT NOT NULL UNIQUE,    -- UUID for external reference
    run_id          TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    finding_id      TEXT REFERENCES findings(finding_id) ON DELETE SET NULL,
    notification_type TEXT NOT NULL CHECK(notification_type IN ('alert', 'warning', 'info', 'success', 'error')),
    severity        TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info')),
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    channels        TEXT,                    -- JSON array of channels sent to
    sent_at         TEXT NOT NULL DEFAULT (datetime('now')),
    status          TEXT NOT NULL DEFAULT 'sent' CHECK(status IN ('pending', 'sent', 'failed', 'retrying')),
    retry_count     INTEGER NOT NULL DEFAULT 0,
    last_retry_at   TEXT,
    error_message   TEXT,
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    expires_at      TEXT,                    -- NULL = no expiration
    metadata        TEXT
);

CREATE INDEX idx_notifications_notification_id ON notifications(notification_id);
CREATE INDEX idx_notifications_run_id ON notifications(run_id);
CREATE INDEX idx_notifications_project_id ON notifications(project_id);
CREATE INDEX idx_notifications_finding_id ON notifications(finding_id);
CREATE INDEX idx_notifications_type ON notifications(notification_type);
CREATE INDEX idx_notifications_severity ON notifications(severity);
CREATE INDEX idx_notifications_status ON notifications(status);
CREATE INDEX idx_notifications_sent_at ON notifications(sent_at);

-- ============================================================================
-- TRIGGERS: Auto-update timestamps
-- ============================================================================

-- Update projects.updated_at on row modification
CREATE TRIGGER trg_projects_updated_at
AFTER UPDATE ON projects
BEGIN
    UPDATE projects SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Update findings.updated_at on row modification
CREATE TRIGGER trg_findings_updated_at
AFTER UPDATE ON findings
BEGIN
    UPDATE findings SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Update agents.updated_at on row modification
CREATE TRIGGER trg_agents_updated_at
AFTER UPDATE ON agents
BEGIN
    UPDATE agents SET updated_at = datetime('now') WHERE id = NEW.id;
END;
