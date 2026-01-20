# PLATFORM GOD - CLI Reference

## Installation

```bash
pip install -e .
```

This installs two entry points:
- `pgod`
- `platform-god`

Both are identical and invoke `platform_god.cli:main`.

## Commands Overview

```
pgod
├── agents          # List available agents
├── chains          # List available chains
├── run             # Execute a chain
├── inspect         # Quick repository inspection
├── history         # Show execution history
├── ui              # Launch the interactive UI
├── monitor         # Show system status dashboard
└── version         # Show version
```

**Note:** To start the API server, use `uvicorn platform_god.api.app:app` directly.

## Command Reference

### `pgod agents`

List all available agents with their classes and permissions.

```bash
pgod agents [OPTIONS]
```

#### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--class` | `-c` | Filter by agent class |
| `--verbose` | `-v` | Show detailed permissions |

#### Examples

```bash
# List all agents
pgod agents

# List only read-only scan agents
pgod agents --class READ_ONLY_SCAN

# Show detailed permissions
pgod agents --verbose

# List planning agents
pgod agents -c PLANNING_SYNTHESIS
```

#### Output Format

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Name                     ┃ Class                 ┃ Permissions      ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ PG_DISCOVERY             │ READ_ONLY_SCAN        │ read_only        │
│ PG_STACKMAP              │ READ_ONLY_SCAN        │ read_only        │
│ PG_HEALTH_SCORE          │ READ_ONLY_SCAN        │ read_only        │
└──────────────────────────┴───────────────────────┴──────────────────┘
```

---

### `pgod chains`

List all available execution chains with their steps.

```bash
pgod chains
```

#### Examples

```bash
pgod chains
```

#### Output Format

```
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Name             ┃ Description                ┃ Steps            ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ discovery_analysis│ Scan repository...        │ 1. PG_DISCOVERY  │
│ security_scan     │ Scan for secrets...       │ 1. PG_DISCOVERY  │
│                  │                            │ 2. PG_SECRETS_...│
└───────────────────┴────────────────────────────┴──────────────────┘
```

---

### `pgod run`

Execute an agent chain against a repository.

```bash
pgod run CHAIN_NAME REPO_PATH [OPTIONS]
```

#### Arguments

| Argument | Description |
|----------|-------------|
| `CHAIN_NAME` | Chain to execute (see aliases below) |
| `REPO_PATH` | Path to the repository to analyze |

#### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--mode` | `-m` | Execution mode | `dry_run` |
| `--output` | `-o` | Output file path | None (stdout) |
| `--record` | `-r` | Record run in state | False |

#### Execution Modes

| Mode | Description | LLM Calls | Writes |
|------|-------------|-----------|--------|
| `dry_run` | Validate prechecks only | No | No |
| `simulated` | Mock outputs from schemas | No | No |
| `live` | Full LLM execution | Yes | Permitted only |

#### Chain Name Aliases

| Primary | Aliases |
|---------|---------|
| `discovery_analysis` | `discovery` |
| `security_scan` | `security` |
| `dependency_audit` | `dependencies`, `deps` |
| `doc_generation` | `docs`, `documentation` |
| `tech_debt` | `debt` |
| `full_analysis` | `full`, `all` |

#### Examples

```bash
# Dry run (validate only)
pgod run discovery /path/to/repo

# Simulated execution (no LLM calls)
pgod run security /path/to/repo --mode simulated

# Full execution with LLM
pgod run full_analysis /path/to/repo --mode live

# Save output to file
pgod run discovery /path/to/repo --mode live -o results/

# Record run for history
pgod run tech_debt /path/to/repo --mode live --record

# Short chain name
pgod run deps /path/to/repo -m live
```

#### Output

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
║  Platform God                                          ║
║  Chain: discovery_analysis                             ║
║  Repository: /path/to/repo                             ║
║  Mode: live                                            ║
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

Chain: discovery_analysis
Status: completed
Steps: 4/4
  [1] ✓ PG_DISCOVERY: completed
      Time: 1523ms
  [2] ✓ PG_STACKMAP: completed
      Time: 892ms
  [3] ✓ PG_HEALTH_SCORE: completed
      Time: 1245ms
  [4] ✓ PG_REPORT_WRITER: completed
      Time: 2102ms

Run recorded: run_20240115123456
Results saved to: results/discovery_analysis_20240115T123456Z.json
```

---

### `pgod inspect`

Quick inspection of repository structure.

```bash
pgod inspect REPO_PATH
```

#### Examples

```bash
pgod inspect /path/to/repo
```

#### Output

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
║  Repository Inspection                                 ║
║  Path: /path/to/repo                                  ║
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃ Extension     ┃  Count ┃ Percent  ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ .py           │    142 │    45.2% │
│ .md           │     58 │    18.5% │
│ .json         │     42 │    13.4% │
│ .yaml         │     38 │    12.1% │
│ .txt          │     24 │     7.6% │
│ (no ext)      │     10 │     3.2% │
└───────────────┴────────┴──────────┘

Total files: 314
Total size: 2,847,392 bytes
```

---

### `pgod history`

Show chain execution history for a repository.

```bash
pgod history REPO_PATH [OPTIONS]
```

#### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--limit` | `-n` | Number of runs to show | 20 |

#### Examples

```bash
# Show last 20 runs
pgod history /path/to/repo

# Show last 5 runs
pgod history /path/to/repo --limit 5
```

#### Output

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
║  Execution History (15 runs)                           ║
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Time               ┃ Chain          ┃ Status   ┃ Duration ┃ Run ID       ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 2024-01-15 12:34    │ full_analysis   │ completed│ 5762ms   │ run_202401… │
│ 2024-01-15 11:20    │ security_scan   │ completed│ 2341ms   │ run_202401… │
│ 2024-01-14 16:45    │ discovery       │ completed│ 1523ms   │ run_202401… │
│ 2024-01-14 09:15    │ tech_debt       │ failed   │ 892ms    │ run_202401… │
└─────────────────────┴────────────────┴──────────┴──────────┴──────────────┘
```

---

### `pgod ui`

Launch the read-only UI (Node.js + Ink).

```bash
pgod ui REPO_PATH [OPTIONS]
```

#### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--dashboard` | `-d` | Launch dashboard mode (TUI) | False |

#### Examples

```bash
# CLI mode (text output)
pgod ui /path/to/repo

# Dashboard mode (interactive TUI)
pgod ui /path/to/repo --dashboard
```

#### Requirements

- Node.js 18+
- UI dependencies installed: `cd ui && npm install`

#### UI Modes

| Mode | Description |
|------|-------------|
| CLI (default) | Text-based output of runs, findings, artifacts |
| Dashboard (`--dashboard`) | Interactive TUI with keyboard navigation |

---

### `pgod version`

Show Platform God version.

```bash
pgod version
```

#### Output

```
Platform God v0.1.0
```

---

### `pgod monitor`

Show system status, health checks, and recent runs.

```bash
pgod monitor [OPTIONS]
```

#### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--health` | `-h` | Show health check status | False |
| `--metrics` | `-m` | Show execution metrics | False |
| `--recent` | `-n` | Number of recent runs | 10 |
| `--watch` | `-w` | Watch mode (auto-refresh) | False |

#### Examples

```bash
# Show health check
pgod monitor --health

# Show recent runs with auto-refresh
pgod monitor --recent 20 --watch
```

---

### `pgod serve`

Start the FastAPI REST API server.

```bash
pgod serve [OPTIONS]
```

#### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Bind address | 127.0.0.1 |
| `--port` | Server port | 8000 |
| `--reload` | Enable auto-reload | False |

#### Examples

```bash
# Start on default port 8000
pgod serve

# Start on custom port
pgod serve --port 8080

# Start with auto-reload for development
pgod serve --reload
```

#### Accessing API Documentation

Once the server is running:
- OpenAPI/Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

---

## Environment Variables

### LLM Configuration

```bash
# Provider selection
export PG_LLM_PROVIDER=anthropic  # anthropic|openai|azure_openai|custom

# API keys
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export PG_LLM_API_KEY=...  # For custom provider

# Model override
export PG_LLM_MODEL=claude-3-5-sonnet-20241022

# Custom endpoint
export PG_LLM_BASE_URL=https://api.example.com
```

### Default Models

| Provider | Default Model |
|----------|---------------|
| anthropic | claude-3-5-sonnet-20241022 |
| openai | gpt-4o |
| azure_openai | gpt-4o |
| custom | custom-model |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Failure (agent or chain failed) |
| 2 | Invalid arguments |
| 127 | Node.js not found (UI command) |

## Output Files

### Chain Results

When using `--output`, results are saved as:

```
{chain_name}_{timestamp}.json
```

Example: `discovery_analysis_20240115T123456Z.json`

### State Storage

State is automatically stored in:

```
var/state/
├── index.json               # Run index
├── runs/
│   └── run_{timestamp}.json # Individual runs
└── repositories/
    └── {repo_hash}.json     # Repository state
```

### Audit Logs

All executions are logged to:

```
var/audit/
└── execution_YYYYMMDD.jsonl
```

## Python API Usage

```python
from pathlib import Path
from platform_god.orchestrator.core import Orchestrator, ChainDefinition
from platform_god.agents.executor import ExecutionMode

# Create orchestrator
orchestrator = Orchestrator()

# Execute chain
chain = ChainDefinition.discovery_chain()
result = orchestrator.execute_chain(
    chain,
    Path("/path/to/repo"),
    mode=ExecutionMode.LIVE
)

# Print summary
print(orchestrator.chain_summary(result))
```
