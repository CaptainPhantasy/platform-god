/**
 * CLI Mode Output - text-based rendering equivalent to existing functionality.
 *
 * Read-only output generators:
 * - Runs list
 * - Latest run summary
 * - Findings grouped by severity
 * - Artifact index
 */

import Table from 'cli-table3';
import chalk from 'chalk';

const { cyan, green, red, yellow, dim, bold, gray } = chalk;

/**
 * Render runs list as a table
 */
function renderRunsList(runs) {
  if (!runs || runs.length === 0) {
    return '\n' + yellow('No runs found') + '\n';
  }

  const table = new Table({
    head: [cyan('Time'), cyan('Chain'), cyan('Status'), cyan('Duration'), dim('Run ID')],
    style: {
      head: [],
      border: ['gray'],
    },
    colWidths: [19, 25, 12, 12, 12],
  });

  for (const run of runs) {
    const statusSymbol = run.status === 'completed' ? green('✓') : red('✗');
    const statusColor = run.status === 'completed' ? green : red;
    const duration = run.execution_time_ms ? `${Math.round(run.execution_time_ms)}ms` : '-';
    const time = run.started_at ? run.started_at.substring(0, 19) : '-';
    const shortId = run.run_id ? run.run_id.substring(0, 10) : '-';

    table.push([
      time,
      run.chain_name || '-',
      statusColor(statusSymbol + ' ' + run.status),
      duration,
      dim(shortId),
    ]);
  }

  return '\n' + table.toString() + '\n';
}

/**
 * Render latest run summary
 */
function renderLatestRunSummary(summary) {
  if (!summary) {
    return '\n' + yellow('No recent runs found') + '\n';
  }

  const statusColor = summary.status === 'completed' ? green : red;
  const lines = [];

  lines.push('\n' + bold('Latest Run Summary'));
  lines.push('─'.repeat(40));
  lines.push(`  Chain:     ${cyan(summary.chain_name || '-')}`);
  lines.push(`  Status:    ${statusColor(summary.status)}`);
  lines.push(`  Started:   ${summary.started_at || '-'}`);
  lines.push(`  Run ID:    ${dim(summary.run_id || '-')}`);

  if (summary.execution_time_ms) {
    lines.push(`  Duration:  ${Math.round(summary.execution_time_ms)}ms`);
  }

  if (summary.agent_count) {
    lines.push(`  Agents:    ${summary.agent_count} step${summary.agent_count > 1 ? 's' : ''}`);
  }

  if (summary.error) {
    lines.push(`  Error:     ${red(summary.error)}`);
  }

  return lines.join('\n') + '\n';
}

/**
 * Render findings grouped by severity
 */
function renderFindings(grouped) {
  if (!grouped) {
    return '\n' + yellow('No findings data available') + '\n';
  }

  const severityOrder = ['critical', 'high', 'medium', 'low', 'info'];
  const severityColors = {
    critical: red,
    high: red,
    medium: yellow,
    low: cyan,
    info: gray,
  };
  const totalFindings = Object.values(grouped).reduce((sum, arr) => sum + arr.length, 0);

  if (totalFindings === 0) {
    return '\n' + green('No findings - all clear!') + '\n';
  }

  const lines = [];

  lines.push('\n' + bold(`Findings (${totalFindings} total)`));
  lines.push('─'.repeat(40));

  for (const severity of severityOrder) {
    const findings = grouped[severity] || [];
    if (findings.length === 0) continue;

    const color = severityColors[severity];
    lines.push(`\n${color(severity.toUpperCase())} (${findings.length}):`);

    for (const finding of findings.slice(0, 10)) {
      const title = finding.title || finding.description || finding.path || 'Untitled';
      const source = finding.path || finding.source || finding.agent || '';
      lines.push(`  • ${title}`);
      if (source) {
        lines.push(`    ${dim(source)}`);
      }
    }

    if (findings.length > 10) {
      lines.push(`  ${dim(`... and ${findings.length - 10} more`)}`);
    }
  }

  return lines.join('\n') + '\n';
}

/**
 * Render artifact index
 */
function renderArtifactsIndex(artifacts) {
  if (!artifacts || artifacts.length === 0) {
    return '\n' + yellow('No artifacts found') + '\n';
  }

  // Group by type
  const byType = {};
  for (const artifact of artifacts) {
    if (!byType[artifact.type]) {
      byType[artifact.type] = [];
    }
    byType[artifact.type].push(artifact);
  }

  const lines = [];

  lines.push('\n' + bold(`Artifacts (${artifacts.length} total)`));
  lines.push('─'.repeat(40));

  for (const [type, items] of Object.entries(byType)) {
    lines.push(`\n${cyan(type)} (${items.length}):`);
    for (const artifact of items.slice(0, 5)) {
      const sizeKB = (artifact.size / 1024).toFixed(1);
      lines.push(`  • ${artifact.path} ${dim(`(${sizeKB}KB, ${artifact.hash.substring(0, 8)}...)`)}`);
    }
    if (items.length > 5) {
      lines.push(`  ${dim(`... and ${items.length - 5} more`)}`);
    }
  }

  return lines.join('\n') + '\n';
}

/**
 * Render repository state
 */
function renderRepositoryState(state) {
  if (!state) {
    return '\n' + yellow('No repository state found') + '\n';
  }

  const lines = [];

  lines.push('\n' + bold('Repository State'));
  lines.push('─'.repeat(40));
  lines.push(`  Created:   ${state.created_at ? state.created_at.substring(0, 19) : '-'}`);
  lines.push(`  Updated:   ${state.updated_at ? state.updated_at.substring(0, 19) : '-'}`);

  if (state.fingerprint) {
    lines.push(`  Files:     ${state.fingerprint.file_count || 0}`);
    lines.push(`  Scanned:   ${state.fingerprint.last_scanned ? state.fingerprint.last_scanned.substring(0, 19) : '-'}`);
  }

  if (state.last_chain_runs && Object.keys(state.last_chain_runs).length > 0) {
    lines.push('\n  Chain Runs:');
    for (const [chain, runId] of Object.entries(state.last_chain_runs)) {
      lines.push(`    ${chain}: ${dim(runId.substring(0, 8))}...`);
    }
  }

  return lines.join('\n') + '\n';
}

/**
 * Render full CLI output
 */
function renderCLIData(data) {
  const lines = [];

  lines.push(bold.cyan('Platform God - Repository Analysis'));
  lines.push(dim(`Repository: ${data.repository.name}`));
  lines.push(dim(`Path: ${data.repository.path}\n`));

  // Latest run summary
  if (data.runs?.latest) {
    lines.push(renderLatestRunSummary(data.runs.latest));
  }

  // Recent runs
  if (data.runs?.recent && data.runs.recent.length > 0) {
    lines.push(bold('Recent Runs'));
    lines.push(renderRunsList(data.runs.recent));
  }

  // Findings
  if (data.findings) {
    lines.push(renderFindings(data.findings));
  }

  // Repository state
  if (data.repositoryState) {
    lines.push(renderRepositoryState(data.repositoryState));
  }

  // Artifacts
  if (data.artifacts && data.artifacts.length > 0) {
    lines.push(renderArtifactsIndex(data.artifacts));
  }

  return lines.join('\n');
}

export default {
  renderRunsList,
  renderLatestRunSummary,
  renderFindings,
  renderArtifactsIndex,
  renderRepositoryState,
  renderCLIData,
};
