# PLATFORM GOD - Style and Conventions

## Code Style

- **Type Annotations**: 100% coverage required for public APIs
- **Docstrings**: All public APIs must be documented
- **Formatting**: Uses `ruff` for code formatting
- **Linting**: Uses `ruff` and `mypy` for type checking

## Naming Conventions

- **Modules**: `snake_case`
- **Classes**: `PascalCase`
- **Functions/Methods**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: Leading underscore `_private`

## Project Patterns

1. **Deterministic Agent Model** - Agents have no discretion, follow strict contracts
2. **Permission Boundaries** - 5 agent classes with graduated permissions
3. **Audit Logging** - All operations logged to `var/audit/`
4. **State Management** - Repository state tracked in `var/state/`
5. **Registry Storage** - Entity storage in `var/registry/`

## Important Constraints

- No breaking changes to agent contracts
- All state must be serializable to JSON
- No circular dependencies between agents
- Registry operations must be atomic
- Audit logs must be append-only
- UI must be strictly read-only
- No parallel execution within chains
- Single-process operation only

## File Structure Conventions

- Agent definitions: `prompts/agents/*.md` with contract format
- State storage: `var/state/runs/` and `var/state/repositories/`
- Audit logs: `var/audit/execution_YYYYMMDD.jsonl`
- Artifacts: `var/artifacts/` for generated reports
