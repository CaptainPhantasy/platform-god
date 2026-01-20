/**
 * Ink Dashboard - Interactive TUI using Ink (React for CLI).
 *
 * Screens:
 * - Runs screen (list, status, duration)
 * - Run detail screen (agent chain execution order)
 * - Findings screen (filterable by severity/category)
 * - Artifacts screen (type, path, hash)
 *
 * Navigation: Keyboard-only, simple list/tab navigation
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Box, Text, useInput, useApp } from 'ink';
import TextInput from 'ink-text-input';

const { cyan, green, red, yellow, gray, dim, bold } = require('chalk');

/**
 * Status indicator component
 */
function Status({ status }) {
  const color = status === 'completed' ? green : status === 'failed' ? red : yellow;
  const symbol = status === 'completed' ? '✓' : status === 'failed' ? '✗' : '○';
  return <Text color={color}>{symbol} {status}</Text>;
}

/**
 * Runs Screen - List of chain runs
 */
export function RunsScreen({ runs, onSelectRun, onBack }) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  useInput((input, key) => {
    if (key.return && runs[selectedIndex]) {
      onSelectRun(runs[selectedIndex].run_id);
    } else if (key.escape) {
      onBack();
    } else if (key.upArrow) {
      setSelectedIndex(i => Math.max(0, i - 1));
    } else if (key.downArrow) {
      setSelectedIndex(i => Math.min(runs.length - 1, i + 1));
    }
  });

  if (!runs || runs.length === 0) {
    return (
      <Box flexDirection="column">
        <Box><Text bold>Runs List</Text></Box>
        <Box><Text color="yellow">No runs found</Text></Box>
        <Box marginTop={1}><Text dim>Press ESC to go back</Text></Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" flexGrow={1}>
      <Box marginBottom={1}>
        <Text bold>Runs List ({runs.length})</Text>
      </Box>

      <Box flexDirection="column" borderStyle="single" padding={1}>
        <Box justifyContent="space-between" width={60}>
          <Text bold color="cyan">Time</Text>
          <Text bold color="cyan">Chain</Text>
          <Text bold color="cyan">Status</Text>
          <Text bold color="cyan">Duration</Text>
        </Box>

        {runs.map((run, idx) => (
          <Box
            key={run.run_id}
            backgroundColor={idx === selectedIndex ? 'gray' : undefined}
            justifyContent="space-between"
            width={60}
            paddingX={1}
          >
            <Text>{run.started_at ? run.started_at.substring(0, 19) : '-'}</Text>
            <Text>{run.chain_name || '-'}</Text>
            <Status status={run.status} />
            <Text>{run.execution_time_ms ? `${Math.round(run.execution_time_ms)}ms` : '-'}</Text>
          </Box>
        ))}
      </Box>

      <Box marginTop={1}>
        <Text dim>↑↓ Navigate | Enter: View Details | ESC: Back</Text>
      </Box>
    </Box>
  );
}

/**
 * Run Detail Screen - Agent chain execution order
 */
export function RunDetailScreen({ run, onBack }) {
  useInput((input, key) => {
    if (key.escape) {
      onBack();
    }
  });

  if (!run) {
    return (
      <Box flexDirection="column">
        <Box><Text bold>Run Details</Text></Box>
        <Box><Text color="red">Run not found</Text></Box>
        <Box marginTop={1}><Text dim>Press ESC to go back</Text></Box>
      </Box>
    );
  }

  const agentResults = run.agent_results || [];

  return (
    <Box flexDirection="column" flexGrow={1}>
      <Box marginBottom={1}>
        <Text bold>Run Details: {run.run_id}</Text>
      </Box>

      <Box flexDirection="column" marginBottom={1}>
        <Box><Text color="cyan">Chain: </Text><Text>{run.chain_name}</Text></Box>
        <Box><Text color="cyan">Status: </Text><Status status={run.status} /></Box>
        <Box><Text color="cyan">Started: </Text><Text>{run.started_at || '-'}</Text></Box>
        {run.execution_time_ms && (
          <Box><Text color="cyan">Duration: </Text><Text>{Math.round(run.execution_time_ms)}ms</Text></Box>
        )}
      </Box>

      <Box marginBottom={1}>
        <Text bold>Agent Steps ({agentResults.length})</Text>
      </Box>

      <Box flexDirection="column" borderStyle="single" padding={1}>
        <Box justifyContent="space-between" width={70}>
          <Text bold color="cyan">#</Text>
          <Text bold color="cyan">Agent</Text>
          <Text bold color="cyan">Status</Text>
          <Text bold color="cyan">Time</Text>
        </Box>

        {agentResults.map((agent, idx) => (
          <Box
            key={idx}
            justifyContent="space-between"
            width={70}
            paddingX={1}
          >
            <Text dim>{idx + 1}</Text>
            <Text>{agent.agent_name || '-'}</Text>
            <Status status={agent.status} />
            <Text>{agent.execution_time_ms ? `${Math.round(agent.execution_time_ms)}ms` : '-'}</Text>
          </Box>
        ))}
      </Box>

      {run.error && (
        <Box marginTop={1}>
          <Text color="red">Error: {run.error}</Text>
        </Box>
      )}

      <Box marginTop={1}>
        <Text dim>Press ESC to go back</Text>
      </Box>
    </Box>
  );
}

/**
 * Findings Screen - Filterable by severity/category
 */
export function FindingsScreen({ findings, onBack }) {
  const [selectedSeverity, setSelectedSeverity] = useState('all');
  const [selectedIndex, setSelectedIndex] = useState(0);

  const severities = ['all', 'critical', 'high', 'medium', 'low', 'info'];

  useInput((input, key) => {
    if (key.tab) {
      const idx = severities.indexOf(selectedSeverity);
      setSelectedSeverity(severities[(idx + 1) % severities.length]);
      setSelectedIndex(0);
    } else if (key.escape) {
      onBack();
    } else if (key.upArrow) {
      setSelectedIndex(i => Math.max(0, i - 1));
    } else if (key.downArrow) {
      const max = getFilteredFindings().length - 1;
      setSelectedIndex(i => Math.min(max, i + 1));
    }
  });

  const getFilteredFindings = () => {
    if (selectedSeverity === 'all') {
      const all = [];
      for (const findings of Object.values(findings || {})) {
        all.push(...findings);
      }
      return all;
    }
    return findings[selectedSeverity] || [];
  };

  const filtered = getFilteredFindings();
  const severityColors = {
    critical: 'red',
    high: 'red',
    medium: 'yellow',
    low: 'cyan',
    info: 'gray',
  };

  return (
    <Box flexDirection="column" flexGrow={1}>
      <Box marginBottom={1}>
        <Text bold>Findings</Text>
      </Box>

      <Box marginBottom={1}>
        <Text color="cyan">Filter: </Text>
        {severities.map(s => (
          <Text
            key={s}
            color={s === selectedSeverity ? 'white' : 'gray'}
            inverse={s === selectedSeverity}
          >
            {' ' + s.toUpperCase() + ' '}
          </Text>
        ))}
        <Text dim> (Tab to switch)</Text>
      </Box>

      {filtered.length === 0 ? (
        <Box flexDirection="column">
          <Box><Text color="yellow">No findings for severity: {selectedSeverity}</Text></Box>
        </Box>
      ) : (
        <Box flexDirection="column" borderStyle="single" padding={1} flexGrow={1}>
          {filtered.map((finding, idx) => (
            <Box
              key={idx}
              backgroundColor={idx === selectedIndex ? 'gray' : undefined}
              flexDirection="column"
              paddingX={1}
              marginBottom={idx < filtered.length - 1 ? 1 : 0}
            >
              <Box>
                <Text color={severityColors[finding.severity] || 'white'}>
                  {(finding.severity || 'info').toUpperCase()}
                </Text>
                <Text> {finding.title || finding.description || 'Untitled'}</Text>
              </Box>
              {finding.path && (
                <Text dim>{finding.path}</Text>
              )}
            </Box>
          ))}
        </Box>
      )}

      <Box marginTop={1}>
        <Text dim>↑↓ Navigate | Tab: Filter | ESC: Back</Text>
      </Box>
    </Box>
  );
}

/**
 * Artifacts Screen - Type, path, hash
 */
export function ArtifactsScreen({ artifacts, onBack }) {
  const [selectedType, setSelectedType] = useState('all');
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Get unique types
  const types = ['all', ...new Set((artifacts || []).map(a => a.type))];

  useInput((input, key) => {
    if (key.tab) {
      const idx = types.indexOf(selectedType);
      setSelectedType(types[(idx + 1) % types.length]);
      setSelectedIndex(0);
    } else if (key.escape) {
      onBack();
    } else if (key.upArrow) {
      setSelectedIndex(i => Math.max(0, i - 1));
    } else if (key.downArrow) {
      const max = getFilteredArtifacts().length - 1;
      setSelectedIndex(i => Math.min(max, i + 1));
    }
  });

  const getFilteredArtifacts = () => {
    if (selectedType === 'all') return artifacts || [];
    return (artifacts || []).filter(a => a.type === selectedType);
  };

  const filtered = getFilteredArtifacts();

  return (
    <Box flexDirection="column" flexGrow={1}>
      <Box marginBottom={1}>
        <Text bold>Artifacts ({(artifacts || []).length} total)</Text>
      </Box>

      <Box marginBottom={1}>
        <Text color="cyan">Filter: </Text>
        {types.slice(0, 6).map(t => (
          <Text
            key={t}
            color={t === selectedType ? 'white' : 'gray'}
            inverse={t === selectedType}
          >
            {' ' + t + ' '}
          </Text>
        ))}
        {types.length > 6 && <Text dim> +{types.length - 6} more</Text>}
        <Text dim> (Tab to switch)</Text>
      </Box>

      {filtered.length === 0 ? (
        <Box flexDirection="column">
          <Box><Text color="yellow">No artifacts for type: {selectedType}</Text></Box>
        </Box>
      ) : (
        <Box flexDirection="column" borderStyle="single" padding={1} flexGrow={1}>
          <Box justifyContent="space-between" width={80}>
            <Text bold color="cyan">Path</Text>
            <Text bold color="cyan">Size</Text>
            <Text bold color="cyan">Hash</Text>
          </Box>

          {filtered.slice(0, 20).map((artifact, idx) => (
            <Box
              key={artifact.path}
              backgroundColor={idx === selectedIndex ? 'gray' : undefined}
              justifyContent="space-between"
              width={80}
              paddingX={1}
            >
              <Text>{artifact.path.length > 50 ? artifact.path.substring(0, 47) + '...' : artifact.path}</Text>
              <Text>{(artifact.size / 1024).toFixed(1)}KB</Text>
              <Text dim>{artifact.hash.substring(0, 8)}</Text>
            </Box>
          ))}

          {filtered.length > 20 && (
            <Box paddingX={1}>
              <Text dim>... and {filtered.length - 20} more</Text>
            </Box>
          )}
        </Box>
      )}

      <Box marginTop={1}>
        <Text dim>↑↓ Navigate | Tab: Filter | ESC: Back</Text>
      </Box>
    </Box>
  );
}

/**
 * Main Dashboard App
 */
export function DashboardApp({ repositoryPath, readers }) {
  const [currentScreen, setCurrentScreen] = useState('runs');
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [findings, setFindings] = useState({});
  const [artifacts, setArtifacts] = useState([]);

  // Load data on mount
  useEffect(() => {
    setRuns(readers.listChainRuns(repositoryPath, 50));
    setFindings(readers.getFindingsGrouped(repositoryPath));
    setArtifacts(readers.getArtifactsIndex());
  }, [repositoryPath, readers]);

  // Load run detail when selected
  useEffect(() => {
    if (selectedRunId) {
      setSelectedRun(readers.getRunDetail(selectedRunId));
    }
  }, [selectedRunId, readers]);

  useInput((input, key) => {
    // Global navigation
    if (key.ctrl && input === 'c') {
      process.exit(0);
    }
  });

  const handleSelectRun = useCallback((runId) => {
    setSelectedRunId(runId);
    setCurrentScreen('detail');
  }, []);

  const handleBack = useCallback(() => {
    setCurrentScreen('runs');
    setSelectedRunId(null);
  }, []);

  return (
    <Box flexDirection="column" padding={1}>
      {/* Header */}
      <Box borderStyle="single" paddingX={1} marginBottom={1}>
        <Text bold>Platform God Dashboard</Text>
        <Text dim> - {repositoryPath}</Text>
      </Box>

      {/* Tab indicator */}
      <Box marginBottom={1}>
        {['runs', 'findings', 'artifacts'].map(tab => {
          const isSelected = currentScreen === tab || (currentScreen === 'detail' && tab === 'runs');
          return (
            <Text
              key={tab}
              color={isSelected ? 'white' : 'gray'}
              inverse={isSelected}
              onClick={() => {
                if (tab === 'runs') {
                  setCurrentScreen('runs');
                  setSelectedRunId(null);
                } else {
                  setCurrentScreen(tab);
                }
              }}
            >
              {' ' + tab.charAt(0).toUpperCase() + tab.slice(1) + ' '}
            </Text>
          );
        })}
        <Text dim> (Click to switch)</Text>
      </Box>

      {/* Content */}
      <Box flexGrow={1}>
        {currentScreen === 'runs' && selectedRunId && selectedRun ? (
          <RunDetailScreen run={selectedRun} onBack={handleBack} />
        ) : currentScreen === 'runs' ? (
          <RunsScreen runs={runs} onSelectRun={handleSelectRun} onBack={() => {}} />
        ) : currentScreen === 'findings' ? (
          <FindingsScreen findings={findings} onBack={() => setCurrentScreen('runs')} />
        ) : currentScreen === 'artifacts' ? (
          <ArtifactsScreen artifacts={artifacts} onBack={() => setCurrentScreen('runs')} />
        ) : null}
      </Box>

      {/* Footer */}
      <Box marginTop={1} borderStyle="single" paddingX={1}>
        <Text dim>Ctrl+C: Quit | Click tabs or use keyboard navigation</Text>
      </Box>
    </Box>
  );
}

export default {
  RunsScreen,
  RunDetailScreen,
  FindingsScreen,
  ArtifactsScreen,
  DashboardApp,
};
