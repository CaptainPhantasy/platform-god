/**
 * Data Readers - read-only access to Platform God state files.
 *
 * Reads from:
 * - var/state/runs/<run_id>.json
 * - var/state/repositories/<repo_hash>.json
 * - var/state/index.json
 * - var/registry/platform_god.db (SQLite)
 *
 * All read operations. No writes. No mutations.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import Database from 'better-sqlite3';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Find the project root (ui/ -> project root)
const PROJECT_ROOT = path.resolve(__dirname, '..');

/**
 * Get the path to var directories
 */
function getVarPaths() {
  return {
    state: path.join(PROJECT_ROOT, 'var', 'state'),
    runs: path.join(PROJECT_ROOT, 'var', 'state', 'runs'),
    repositories: path.join(PROJECT_ROOT, 'var', 'state', 'repositories'),
    registry: path.join(PROJECT_ROOT, 'var', 'registry'),
    artifacts: path.join(PROJECT_ROOT, 'artifacts'),
  };
}

/**
 * Read and parse a JSON file safely
 */
function readJson(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    if (error.code !== 'ENOENT') {
      // File exists but failed to parse - return null
      return null;
    }
    return null;
  }
}

/**
 * Read the global state index
 */
function readStateIndex() {
  const { state } = getVarPaths();
  const indexPath = path.join(state, 'index.json');
  return readJson(indexPath) || { runs: [], repositories: [] };
}

/**
 * Get repository hash for a path
 */
function getRepoHash(repositoryRoot) {
  const crypto = require('crypto');
  const resolvedPath = path.resolve(repositoryRoot);
  return crypto.createHash('md5').update(resolvedPath).digest('hex').substring(0, 12);
}

/**
 * Read a chain run by ID
 */
function readChainRun(runId) {
  const { runs } = getVarPaths();
  const runPath = path.join(runs, `${runId}.json`);
  return readJson(runPath);
}

/**
 * List chain runs, optionally filtered by repository
 */
function listChainRuns(repositoryRoot = null, limit = 50) {
  const index = readStateIndex();
  const runIds = index.runs || [];
  const runs = [];

  for (const runId of runIds.slice(0, limit)) {
    const run = readChainRun(runId);
    if (run) {
      if (!repositoryRoot || run.repository_root === path.resolve(repositoryRoot)) {
        runs.push(run);
      }
    }
  }

  return runs;
}

/**
 * Read repository state
 */
function readRepositoryState(repositoryRoot) {
  const repoHash = getRepoHash(repositoryRoot);
  const { repositories } = getVarPaths();
  const repoPath = path.join(repositories, `${repoHash}.json`);
  return readJson(repoPath);
}

/**
 * Get findings grouped by severity
 */
function getFindingsGrouped(repositoryRoot) {
  const state = readRepositoryState(repositoryRoot);
  if (!state || !state.accumulated_findings) {
    return { critical: [], high: [], medium: [], low: [], info: [] };
  }

  const grouped = { critical: [], high: [], medium: [], low: [], info: [] };

  for (const finding of state.accumulated_findings) {
    const severity = (finding.severity || 'info').toLowerCase();
    if (grouped[severity]) {
      grouped[severity].push(finding);
    } else {
      grouped.info.push(finding);
    }
  }

  return grouped;
}

/**
 * Read registry data from SQLite
 */
function readRegistryData() {
  const { registry } = getVarPaths();
  const dbPath = path.join(registry, 'platform_god.db');

  if (!fs.existsSync(dbPath)) {
    return { entities: [], auditLogs: [] };
  }

  let db;
  try {
    db = new Database(dbPath, { readonly: true });
    const entities = [];
    const auditLogs = [];

    // Try to read entities table
    try {
      const entityRows = db.prepare('SELECT * FROM entities').all();
      for (const row of entityRows) {
        try {
          entities.push({
            ...row,
            data: row.data ? JSON.parse(row.data) : null,
          });
        } catch (e) {
          entities.push(row);
        }
      }
    } catch (e) {
      // Table might not exist
    }

    // Try to read audit_logs table
    try {
      const auditRows = db.prepare('SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100').all();
      for (const row of auditRows) {
        try {
          auditLogs.push({
            ...row,
            metadata: row.metadata ? JSON.parse(row.metadata) : null,
          });
        } catch (e) {
          auditLogs.push(row);
        }
      }
    } catch (e) {
      // Table might not exist
    }

    return { entities, auditLogs };
  } finally {
    if (db) db.close();
  }
}

/**
 * Get artifacts index
 */
function getArtifactsIndex() {
  const { artifacts } = getVarPaths();

  if (!fs.existsSync(artifacts)) {
    return [];
  }

  const artifactsList = [];

  function scanDir(dir, prefix = '') {
    const entries = fs.readdirSync(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      const relativePath = path.join(prefix, entry.name);

      if (entry.isDirectory()) {
        scanDir(fullPath, relativePath);
      } else if (entry.isFile()) {
        const stats = fs.statSync(fullPath);
        const crypto = require('crypto');
        const content = fs.readFileSync(fullPath);
        const hash = crypto.createHash('sha256').update(content).digest('hex').substring(0, 16);

        artifactsList.push({
          path: relativePath,
          fullPath: fullPath,
          type: path.extname(entry.name).substring(1),
          size: stats.size,
          hash: hash,
          modified: stats.mtime.toISOString(),
        });
      }
    }
  }

  try {
    scanDir(artifacts);
  } catch (e) {
    // Directory might not exist or be inaccessible
  }

  return artifactsList;
}

/**
 * Get latest run summary for a repository
 */
function getLatestRunSummary(repositoryRoot) {
  const runs = listChainRuns(repositoryRoot, 1);
  if (runs.length === 0) {
    return null;
  }

  const run = runs[0];
  return {
    run_id: run.run_id,
    chain_name: run.chain_name,
    status: run.status,
    started_at: run.started_at,
    completed_at: run.completed_at,
    execution_time_ms: run.execution_time_ms,
    agent_count: run.agent_results?.length || 0,
    error: run.error,
  };
}

/**
 * Get run detail with agent steps
 */
function getRunDetail(runId) {
  const run = readChainRun(runId);
  if (!run) {
    return null;
  }

  return {
    run_id: run.run_id,
    chain_name: run.chain_name,
    repository_root: run.repository_root,
    status: run.status,
    started_at: run.started_at,
    completed_at: run.completed_at,
    execution_time_ms: run.execution_time_ms,
    agent_results: (run.agent_results || []).map((agent, idx) => ({
      step: idx + 1,
      agent_name: agent.agent_name,
      status: agent.status,
      execution_time_ms: agent.execution_time_ms,
      error: agent.error,
    })),
    final_state: run.final_state,
    error: run.error,
  };
}

/**
 * Check if state directory exists
 */
function hasStateData() {
  const { state } = getVarPaths();
  return fs.existsSync(state);
}

/**
 * Get UI data bundle for CLI mode
 */
function getCLIData(repositoryRoot = '.') {
  const resolvedRoot = path.resolve(repositoryRoot);

  return {
    repository: {
      path: resolvedRoot,
      name: path.basename(resolvedRoot),
    },
    runs: {
      latest: getLatestRunSummary(resolvedRoot),
      recent: listChainRuns(resolvedRoot, 10).map(r => ({
        run_id: r.run_id,
        chain_name: r.chain_name,
        status: r.status,
        started_at: r.started_at,
        execution_time_ms: r.execution_time_ms,
      })),
    },
    findings: getFindingsGrouped(resolvedRoot),
    repositoryState: readRepositoryState(resolvedRoot),
    artifacts: getArtifactsIndex(),
  };
}

export default {
  // State readers
  readStateIndex,
  readChainRun,
  listChainRuns,
  readRepositoryState,
  getFindingsGrouped,
  getLatestRunSummary,
  getRunDetail,
  getCLIData,

  // Registry readers
  readRegistryData,
  getArtifactsIndex,

  // Utilities
  getRepoHash,
  getVarPaths,
  hasStateData,
  PROJECT_ROOT,
};
