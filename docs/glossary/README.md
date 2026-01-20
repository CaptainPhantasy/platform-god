# Glossary

## Core Platform God Terms

### Agent
A deterministic task executor defined by a prompt contract in `prompts/agents/`. Agents have specific permission levels and follow strict operating rules.

### Chain
A predefined sequence of agent executions with state passing between steps. Chains orchestrate multi-agent workflows for repository analysis.

### AgentClass
Permission level defining what an agent can read/write:
- `READ_ONLY_SCAN`: Repository scanning and analysis
- `PLANNING_SYNTHESIS`: Planning and synthesis tasks
- `REGISTRY_STATE`: Registry and audit log writes
- `WRITE_GATED`: Controlled artifact generation
- `CONTROL_PLANE`: Full system orchestration

### ExecutionMode
- `dry_run`: Validate prechecks only, no LLM calls
- `simulated`: Mock outputs from schemas, no LLM calls
- `live`: Full LLM execution with all side effects

### Registry
Persistent entity storage in `var/registry/` for tracking state across runs.

### State
Cross-run state storage in `var/state/` including run history and repository fingerprints.

### Audit Log
Execution records stored in `var/audit/` for compliance and forensic analysis.

### PermissionLevel
- `read_only`: No write access
- `write_gated`: Controlled write access to specific paths
- `control_plane`: Full system access
