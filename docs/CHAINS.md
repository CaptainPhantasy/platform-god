# PLATFORM GOD - Chain Reference

## Chain Definitions

Chains are predefined sequences of agent executions with state passing between steps. Each chain is defined as a `ChainDefinition` containing:

- `name`: Chain identifier
- `description`: Human-readable description
- `steps`: Ordered list of `AgentStep` objects
- `initial_state`: Starting state dictionary

## Step Ordering

Each `AgentStep` specifies:

```python
@dataclass
class AgentStep:
    agent_name: str              # Agent to execute
    input_mapping: str | None     # JSONPath expression for input
    output_key: str | None        # Key to store output
    continue_on_failure: bool     # Whether to continue on failure
```

### Input Mapping Syntax

| Mapping | Behavior |
|---------|----------|
| `null` | Use `initial_state` as input |
| `"$.key"` | Extract `key` from chain state |
| `"$.a,$.b"` | Merge multiple keys from state |

### State Flow

```
initial_state
     │
     ▼
┌──────────────┐
│  Step 1      │ input=null → output stored at output_key_1
└──────────────┘
     │
     ▼
┌──────────────┐
│  Step 2      │ input="$.output_key_1" → output stored at output_key_2
└──────────────┘
     │
     ▼
    final_state (contains all output_key values)
```

## Available Chains

### 1. discovery_analysis

**Description**: Scan repository and generate initial report

**Steps**:
| # | Agent | Input Mapping | Output Key | Continue on Failure |
|---|-------|---------------|------------|---------------------|
| 1 | PG_DISCOVERY | null | discovery | No |
| 2 | PG_STACKMAP | $.discovery | stackmap | No |
| 3 | PG_HEALTH_SCORE | $.stackmap | health | No |
| 4 | PG_REPORT_WRITER | $.discovery,$.stackmap,$.health | report | No |

**Expected Outputs**:
- `discovery`: Complete file inventory
- `stackmap`: Technology stack mapping
- `health`: Repository health metrics
- `report`: Consolidated analysis report

**Aliases**: `discovery`, `discovery_analysis`

---

### 2. security_scan

**Description**: Scan for secrets and security risks

**Steps**:
| # | Agent | Input Mapping | Output Key | Continue on Failure |
|---|-------|---------------|------------|---------------------|
| 1 | PG_DISCOVERY | null | discovery | No |
| 2 | PG_SECRETS_AND_RISK | $.discovery | security | No |
| 3 | PG_NEXT_STEPS | $.security | recommendations | No |

**Expected Outputs**:
- `discovery`: File inventory
- `security`: Secret and risk findings
- `recommendations`: Remediation recommendations

**Aliases**: `security`, `security_scan`

---

### 3. dependency_audit

**Description**: Analyze dependencies for vulnerabilities and issues

**Steps**:
| # | Agent | Input Mapping | Output Key | Continue on Failure |
|---|-------|---------------|------------|---------------------|
| 1 | PG_DISCOVERY | null | discovery | No |
| 2 | PG_DEPENDENCY | $.discovery | dependencies | No |
| 3 | PG_SECRETS_AND_RISK | $.dependencies | risk | No |
| 4 | PG_REPORT_WRITER | $.dependencies,$.risk | report | No |

**Expected Outputs**:
- `discovery`: File inventory
- `dependencies`: Dependency analysis
- `risk`: Vulnerability assessment
- `report`: Consolidated audit report

**Aliases**: `dependencies`, `deps`, `dependency_audit`

---

### 4. doc_generation

**Description**: Generate documentation from code analysis

**Steps**:
| # | Agent | Input Mapping | Output Key | Continue on Failure |
|---|-------|---------------|------------|---------------------|
| 1 | PG_DISCOVERY | null | discovery | No |
| 2 | PG_STACKMAP | $.discovery | stackmap | No |
| 3 | PG_ENGINEERING_PRINCIPLES | $.stackmap | principles | No |
| 4 | PG_DOC_AUDIT | $.discovery,$.principles | doc_audit | No |
| 5 | PG_DOC_MANAGER | $.doc_audit | documentation | No |

**Expected Outputs**:
- `discovery`: File inventory
- `stackmap`: Technology stack
- `principles`: Engineering principles extracted
- `doc_audit`: Documentation gaps identified
- `documentation`: Generated documentation

**Aliases**: `docs`, `documentation`, `doc_generation`

---

### 5. tech_debt

**Description**: Analyze technical debt and generate remediation plan

**Steps**:
| # | Agent | Input Mapping | Output Key | Continue on Failure |
|---|-------|---------------|------------|---------------------|
| 1 | PG_DISCOVERY | null | discovery | No |
| 2 | PG_STACKMAP | $.discovery | stackmap | No |
| 3 | PG_HEALTH_SCORE | $.stackmap | health | No |
| 4 | PG_REFACTOR_PLANNER | $.health | refactor_plan | No |
| 5 | PG_NEXT_STEPS | $.refactor_plan | next_steps | No |

**Expected Outputs**:
- `discovery`: File inventory
- `stackmap`: Technology stack
- `health`: Repository health metrics
- `refactor_plan`: Refactoring plan
- `next_steps`: Actionable next steps

**Aliases**: `debt`, `tech_debt`

---

### 6. full_analysis

**Description**: Complete repository analysis with all metrics

**Steps**:
| # | Agent | Input Mapping | Output Key | Continue on Failure |
|---|-------|---------------|------------|---------------------|
| 1 | PG_DISCOVERY | null | discovery | No |
| 2 | PG_STACKMAP | $.discovery | stackmap | No |
| 3 | PG_HEALTH_SCORE | $.stackmap | health | No |
| 4 | PG_DEPENDENCY | $.discovery | dependencies | No |
| 5 | PG_SECRETS_AND_RISK | $.discovery | security | No |
| 6 | PG_DOC_AUDIT | $.discovery | docs | No |
| 7 | PG_RELEASE_READINESS | $.health,$.security | readiness | No |
| 8 | PG_REPORT_WRITER | $.discovery,$.stackmap,$.health,$.dependencies,$.security,$.docs,$.readiness | report | No |

**Expected Outputs**:
- `discovery`: File inventory
- `stackmap`: Technology stack
- `health`: Repository health
- `dependencies`: Dependency analysis
- `security`: Security findings
- `docs`: Documentation audit
- `readiness`: Release readiness assessment
- `report`: Comprehensive final report

**Aliases**: `full`, `all`, `full_analysis`

## Expected Outputs by Chain

| Chain | Primary Output Keys | Output Type |
|-------|---------------------|-------------|
| discovery_analysis | discovery, stackmap, health, report | Analysis report |
| security_scan | discovery, security, recommendations | Security findings |
| dependency_audit | discovery, dependencies, risk, report | Dependency audit |
| doc_generation | discovery, stackmap, principles, doc_audit, documentation | Documentation |
| tech_debt | discovery, stackmap, health, refactor_plan, next_steps | Remediation plan |
| full_analysis | All keys above + readiness | Comprehensive report |

## Read-Only vs Write-Gated Chains

### Read-Only Chains

All default chains are **read-only** - they use agents with:
- `READ_ONLY_SCAN` class
- `PLANNING_SYNTHESIS` class

These chains:
- Do not modify any files
- Only read and analyze the repository
- Produce JSON output to stdout or file

### Write-Gated Chains

To create write-gated chains, use agents with:
- `WRITE_GATED` class
- `CONTROL_PLANE` class

Write-gated chains:
- Can modify `prompts/` and `var/` directories
- Require explicit execution mode selection
- Write operations are logged to audit trail

## Chain Execution Modes

| Mode | Description | LLM Calls | File Writes |
|------|-------------|-----------|-------------|
| DRY_RUN | Validate prechecks only | No | No |
| SIMULATED | Mock outputs from schemas | No | No |
| LIVE | Full execution | Yes | Permitted only |

## Chain Results

All chains return a `ChainResult`:

```python
@dataclass
class ChainResult:
    chain_name: str
    status: ChainStopReason      # completed, agent_failed, etc.
    completed_steps: int
    total_steps: int
    results: list[AgentResult]
    final_state: dict[str, Any]  # All output_key values
    error: str | None
```

### Status Values

| Status | Description |
|--------|-------------|
| `completed` | All steps finished successfully |
| `agent_failed` | An agent returned failure status |
| `precheck_failed` | Precheck validation failed |
| `stop_condition` | Agent stop condition triggered |
| `manual` | Manually stopped |

## Listing Chains

### Via CLI

```bash
# List all chains
pgod chains
```

Output:
```
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Name             ┃ Description                ┃ Steps            ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ discovery_analysis│ Scan repository...        │ 1. PG_DISCOVERY  │
│                   │                            │ 2. PG_STACKMAP   │
│                   │                            │ 3. PG_HEALTH_SCORE│
│                   │                            │ 4. PG_REPORT_WRITER│
└───────────────────┴────────────────────────────┴──────────────────┘
```

### Via Python API

```python
from platform_god.orchestrator.core import ChainDefinition

chains = [
    ChainDefinition.discovery_chain(),
    ChainDefinition.security_scan_chain(),
    ChainDefinition.dependency_audit_chain(),
    ChainDefinition.doc_generation_chain(),
    ChainDefinition.tech_debt_chain(),
    ChainDefinition.full_analysis_chain(),
]

for chain in chains:
    print(f"{chain.name}: {len(chain.steps)} steps")
```

## Custom Chains

Create custom chains by composing steps:

```python
from platform_god.orchestrator.core import ChainDefinition, AgentStep

custom_chain = ChainDefinition(
    name="custom_audit",
    description="Custom audit chain",
    steps=[
        AgentStep(agent_name="PG_DISCOVERY", output_key="discovery"),
        AgentStep(agent_name="PG_DEPENDENCY", input_mapping="$.discovery", output_key="deps"),
    ],
    initial_state={"repository_root": "/path/to/repo"}
)
```
