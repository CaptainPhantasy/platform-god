# PLATFORM GOD - Project Overview

## Purpose

PLATFORM GOD is a deterministic, agent-driven repository governance and analysis framework. It provides automated codebase analysis, state tracking, and governance through a multi-agent orchestration system with 34 specialized agents and 6 predefined chains.

## Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI for REST API
- **CLI**: Typer + Rich for terminal output
- **Testing**: pytest
- **LLM**: Anthropic Claude or OpenAI APIs
- **UI**: Node.js + Ink (React for CLI) - read-only TUI

## Key Directories

- `src/platform_god/` - Core Python application (~20K LOC)
  - `agents/` - Agent registry & execution harness
  - `api/` - FastAPI REST API (routes, middleware, schemas)
  - `orchestrator/` - Chain orchestration
  - `state/` - State persistence
  - `registry/` - Entity registry storage
  - `llm/` - LLM client abstraction
  - `core/` - Data models & exceptions
  - `cli.py` - Command-line interface
  - `dashboard.py` - TUI dashboard (textual)
- `prompts/agents/` - 34 agent prompt definitions
- `docs/` - Documentation
- `tests/` - Test suite (284 tests)
- `var/` - Runtime storage (registry, state, audit, artifacts)

## Execution Modes

1. **DRY_RUN** - Validate only, no LLM execution
2. **SIMULATED** - Mock output based on schema
3. **LIVE** - Full LLM execution

## Agent Classes (Permission Levels)

1. **READ_ONLY_SCAN** - Repository scanning, analysis
2. **PLANNING_SYNTHESIS** - Planning, synthesis
3. **REGISTRY_STATE** - Write to var/registry/, var/audit/
4. **WRITE_GATED** - Write to prompts/, var/artifacts/, var/cache/
5. **CONTROL_PLANE** - Full write to var/, prompts/agents/

## Predefined Chains

- `discovery_analysis` - Initial scan
- `security_scan` - Security risks
- `dependency_audit` - Vulnerabilities
- `doc_generation` - Documentation
- `tech_debt` - Remediation plan
- `full_analysis` - Complete 8-step pipeline
