# Dashboard Documentation

The Platform God dashboard provides terminal-based UI for monitoring and interacting with the system.

## UI Implementation

The dashboard is implemented in the `ui/` directory using:
- **Node.js 18+** runtime
- **Ink** - React for CLI
- **Terminal-based rendering** with Rich output

## Launching the Dashboard

```bash
# Start dashboard for a repository
pgod ui /path/to/repo --dashboard

# The UI provides interactive browsing of:
# - Chain runs and history
# - Agent executions
# - Generated artifacts
# - System status
```

## Requirements

### Node.js Dependencies

```bash
cd ui/
npm install
```

### System Requirements

- Node.js 18 or higher
- 80x24 terminal minimum (larger recommended)
- UTF-8 encoding support

## Dashboard Features

### Interactive Mode (`--dashboard`)

- **Real-time updates**: Watch runs as they execute
- **Keyboard navigation**: Browse runs, artifacts, and logs
- **Search**: Filter runs by chain, status, date
- **Detail views**: Inspect individual agent outputs

### CLI Mode (default)

Text-based output without interaction:
```bash
pgod ui /path/to/repo
```

## Keyboard Shortcuts (Interactive Mode)

| Key | Action |
|-----|--------|
| `q` | Quit dashboard |
| `↑`/`↓` | Navigate list |
| `Enter` | View details |
| `/` | Search |
| `n` | Next page |
| `p` | Previous page |
| `r` | Refresh data |

## Troubleshooting

### Dashboard Won't Start

```bash
# Check Node.js version
node --version  # Should be 18+

# Verify dependencies
cd ui && npm list

# Check for syntax errors
node --check index.js
```

### Display Issues

If the terminal looks corrupted:
- Increase terminal size (recommended: 120x40)
- Ensure UTF-8 encoding: `export LANG=en_US.UTF-8`
- Try different terminal emulator (iTerm2, Terminal.app)

### Performance

For large repositories:
- Use filters to limit displayed runs
- Reduce refresh rate
- Consider using CLI mode instead: `pgod ui /path/to/repo`

## Development

### Running UI in Development

```bash
cd ui/
npm run dev  # Auto-reload on changes
```

### Building for Production

```bash
cd ui/
npm run build
```

## Known Limitations

- Dashboard is read-only (no command execution)
- Large run histories may be slow to load
- Network repositories not supported
- Requires local filesystem access
