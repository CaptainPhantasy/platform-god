# Platform God UI

Read-only UI for Platform God - Node.js + Ink.

## READ-ONLY GUARANTEE

This UI is **strictly read-only**. It:
- **NEVER writes** to any files
- **NEVER modifies** state
- **NEVER executes** agents
- **NEVER triggers** orchestration
- **ONLY reads** from existing state files

The UI is a **consumer** of data, never a controller. It can be completely removed without affecting core Platform God functionality.

## Installation

```bash
cd ui
npm install
```

Requires Node.js 18+.

## Usage

### CLI Mode (Text Output)

```bash
# From project root
pgod ui .

# Or directly with node
node ui/index.js --repo /path/to/repo
```

Output includes:
- Latest run summary
- Recent runs list
- Findings grouped by severity
- Artifact index
- Repository state

### Dashboard Mode (Ink TUI)

```bash
# From project root
pgod ui . --dashboard

# Or directly with node
node ui/index.js --repo /path/to/repo --dashboard
```

**Navigation:**
- **Tabs**: Click to switch between Runs, Findings, Artifacts
- **Runs Screen**: ↑↓ to navigate, Enter to view details, ESC to back
- **Findings Screen**: Tab to filter by severity, ↑↓ to navigate
- **Artifacts Screen**: Tab to filter by type, ↑↓ to navigate
- **Ctrl+C**: Quit

## Data Sources

The UI reads from:

| Source | Path | Contents |
|--------|------|----------|
| State | `var/state/index.json` | Global run index |
| State | `var/state/runs/<run_id>.json` | Individual chain runs |
| State | `var/state/repositories/<hash>.json` | Repository state |
| Registry | `var/registry/platform_god.db` | SQLite registry (read-only) |
| Artifacts | `artifacts/` | Generated artifacts |

## Architecture

```
ui/
├── index.js           # Entry point, mode selection
├── package.json       # Dependencies
├── lib/
│   ├── readers.js     # Read-only data access
│   ├── cli-output.js  # CLI mode rendering
│   └── ink-dashboard.js  # Ink TUI components
└── README.md          # This file
```

## Decoupling

The UI is completely decoupled from core Platform God:

- No imports of Python agent/orchestrator code
- No dependency on `src/platform_god/` modules
- Standalone Node.js process
- Communicates via shared file formats (JSON, SQLite)

This means the UI can:
- Be removed without breaking core functionality
- Be replaced with another implementation
- Run independently (once state data exists)

## Removed Components

The following Textual-based components were removed:

- `src/platform_god/dashboard/__init__.py`
- `src/platform_god/dashboard/app.py`

## File List: Removed/Archived Textual Components

```
REMOVED:
  src/platform_god/dashboard/__init__.py
  src/platform_god/dashboard/app.py
```

## Confirmation: Read-Only

**This UI is read-only.**

- ✅ No file writes
- ✅ No state mutation
- ✅ No agent execution
- ✅ No orchestration logic
- ✅ No background processes
- ✅ No polling
- ✅ No network requests

The UI solely displays data that already exists in `var/state/`, `var/registry/`, and `artifacts/`.
