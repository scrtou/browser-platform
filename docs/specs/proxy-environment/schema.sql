-- Browser Platform v1.1: proposed adapter-owned metadata, for an EMPTY database.
-- This is not a migration for section 16's earlier schema or SealSkin's YAML.
-- Execute foreign_keys=ON on EVERY connection; use short write transactions.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Revisions are immutable. API edits insert a new revision, then update a
-- stopped profile's references in one transaction. Never edit a live revision.
CREATE TABLE proxies (
    id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('http', 'https', 'socks5')),
    host TEXT NOT NULL CHECK (length(host) > 0),
    port INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
    username_secret_ref TEXT,
    password_secret_ref TEXT,
    country TEXT, -- administrative expectation; NOT a measured location
    region TEXT,
    city TEXT,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (id, revision),
    CHECK ((username_secret_ref IS NULL) = (password_secret_ref IS NULL)),
    CHECK (country IS NULL OR length(country) = 2)
);

CREATE TABLE network_policies (
    id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    mode TEXT NOT NULL CHECK (mode IN ('direct', 'proxy_required')),
    dns_mode TEXT NOT NULL CHECK (dns_mode IN ('upstream', 'approved_resolver')),
    webrtc_policy TEXT NOT NULL CHECK (webrtc_policy IN ('disabled', 'relay_only')),
    ipv6_policy TEXT NOT NULL CHECK (ipv6_policy IN ('blocked', 'enforced')),
    config_json TEXT NOT NULL CHECK (json_valid(config_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (id, revision),
    UNIQUE (id, revision, mode),
    CHECK ((mode = 'proxy_required' AND dns_mode = 'upstream') OR
           (mode = 'direct' AND dns_mode = 'approved_resolver'))
);

CREATE TABLE browser_environments (
    id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    name TEXT NOT NULL,
    engine TEXT NOT NULL CHECK (engine IN ('chromium', 'camoufox')),
    spec_json TEXT NOT NULL CHECK (json_valid(spec_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (id, revision),
    UNIQUE (id, revision, engine)
);

-- A materialized, immutable, secret-free result of engine-specific generation.
-- Hash the exact stored UTF-8 artifact bytes; no cross-language reserialization.
CREATE TABLE environment_artifacts (
    id TEXT PRIMARY KEY,
    environment_id TEXT NOT NULL,
    environment_revision INTEGER NOT NULL,
    engine TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL CHECK (
        length(artifact_sha256) = 64 AND artifact_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    artifact_json TEXT NOT NULL CHECK (json_valid(artifact_json)),
    engine_version TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    worker_image_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (id, environment_id, environment_revision, engine),
    FOREIGN KEY (environment_id, environment_revision, engine)
        REFERENCES browser_environments (id, revision, engine) ON DELETE RESTRICT
);

CREATE TABLE profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    engine TEXT NOT NULL CHECK (engine IN ('chromium', 'camoufox')),
    persistent_home TEXT NOT NULL UNIQUE,
    proxy_id TEXT,
    proxy_revision INTEGER,
    network_policy_id TEXT NOT NULL,
    network_policy_revision INTEGER NOT NULL,
    network_mode TEXT NOT NULL CHECK (network_mode IN ('direct', 'proxy_required')),
    environment_id TEXT NOT NULL,
    environment_revision INTEGER NOT NULL,
    environment_artifact_id TEXT, -- NULL only while the environment is a draft
    start_url TEXT NOT NULL,
    idle_policy_json TEXT NOT NULL CHECK (json_valid(idle_policy_json)),
    resource_limits_json TEXT NOT NULL CHECK (json_valid(resource_limits_json)),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    config_revision INTEGER NOT NULL CHECK (config_revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (proxy_id, proxy_revision)
        REFERENCES proxies (id, revision) ON DELETE RESTRICT,
    FOREIGN KEY (network_policy_id, network_policy_revision, network_mode)
        REFERENCES network_policies (id, revision, mode) ON DELETE RESTRICT,
    FOREIGN KEY (environment_id, environment_revision, engine)
        REFERENCES browser_environments (id, revision, engine) ON DELETE RESTRICT,
    FOREIGN KEY (environment_artifact_id, environment_id, environment_revision, engine)
        REFERENCES environment_artifacts (id, environment_id, environment_revision, engine)
        ON DELETE RESTRICT,
    CHECK ((network_mode = 'direct' AND proxy_id IS NULL AND proxy_revision IS NULL) OR
           (network_mode = 'proxy_required' AND proxy_id IS NOT NULL AND
            proxy_revision IS NOT NULL AND proxy_revision > 0))
);

-- One durable launch claim per profile, NOT a replacement for SealSkin sessions.
-- UNKNOWN retains the claim. Never expire it solely because a timeout elapsed.
CREATE TABLE runtime_bindings (
    profile_id TEXT PRIMARY KEY REFERENCES profiles (id) ON DELETE RESTRICT,
    operation_id TEXT NOT NULL UNIQUE,
    orchestrator TEXT NOT NULL CHECK (orchestrator IN ('sealskin', 'docker')),
    external_session_id TEXT,
    generation INTEGER NOT NULL CHECK (generation > 0),
    claim_state TEXT NOT NULL CHECK (claim_state IN ('pending', 'bound', 'unknown', 'releasing')),
    launch_snapshot_json TEXT NOT NULL CHECK (json_valid(launch_snapshot_json)),
    network_policy_digest TEXT,
    acquired_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (orchestrator, external_session_id)
);

-- Dynamic exits require per-profile/per-operation observations, not one global
-- lastPublicIp on a proxy shared by multiple sessions.
CREATE TABLE proxy_observations (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles (id) ON DELETE RESTRICT,
    operation_id TEXT NOT NULL,
    proxy_id TEXT,
    proxy_revision INTEGER,
    network_policy_id TEXT NOT NULL,
    network_policy_revision INTEGER NOT NULL,
    measured_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    probe_endpoint_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pass', 'fail', 'unknown')),
    public_ipv4 TEXT,
    public_ipv6 TEXT,
    latency_ms INTEGER CHECK (latency_ms >= 0),
    country TEXT,
    region TEXT,
    city TEXT,
    geo_source TEXT,
    geo_confidence TEXT CHECK (geo_confidence IN ('high', 'low', 'unknown')),
    error_code TEXT,
    FOREIGN KEY (proxy_id, proxy_revision) REFERENCES proxies (id, revision),
    FOREIGN KEY (network_policy_id, network_policy_revision)
        REFERENCES network_policies (id, revision),
    CHECK ((proxy_id IS NULL) = (proxy_revision IS NULL))
);
CREATE INDEX proxy_observations_latest ON proxy_observations (profile_id, measured_at DESC);

CREATE TABLE health_reports (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles (id) ON DELETE RESTRICT,
    operation_id TEXT,
    checked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    overall TEXT NOT NULL CHECK (overall IN ('healthy', 'degraded', 'unhealthy', 'unknown', 'offline')),
    report_json TEXT NOT NULL CHECK (json_valid(report_json))
);
CREATE INDEX health_reports_latest ON health_reports (profile_id, checked_at DESC);

CREATE TABLE audit_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    profile_id TEXT,
    operation_id TEXT,
    event TEXT NOT NULL,
    details_json TEXT NOT NULL CHECK (json_valid(details_json))
);

-- The service still validates IDs, paths/symlinks, URLs, secret-ref syntax,
-- capability support, JSON shape and ranges, revision immutability, stopped-only
-- edits, observation freshness, and artifact hashes. SQL alone cannot enforce
-- the external runtime's singleton or the host network's egress policy.
