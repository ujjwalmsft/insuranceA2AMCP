# Insurance Claims Processing Agents

This directory contains the insurance claims processing system built with:
- **A2A Protocol**: Agent-to-Agent communication
- **MCP Protocol**: Model Context Protocol for Cosmos DB querying
- **Semantic Kernel**: Agent creation and management
- **Azure AI Foundry**: Agent deployment platform

## Agent Architecture

### Orchestrator
- **claims_assist_agent/**: Main orchestrator that plans DAG and routes work between specialist agents

### Specialist Agents
- **claims_intake_clarifier_agent/**: Validates claim submissions for completeness and consistency
- **doc_intelligence_agent/**: Processes documents and extracts structured data with evidence spans
- **coverage_rules_agent/**: Evaluates claims against policy rules and benefit coverage

### User Interface
- **insurance_agents_registry_dashboard/**: Professional web interface for claim processing employees

## Workflow
1. **End Customer**: Submits claim (Outpatient/Inpatient) with documents
2. **Employee**: Initiates processing via professional dashboard
3. **ClaimsAssist**: Orchestrates specialist agents via A2A protocol
4. **Agents**: Process claim using MCP tools for Cosmos DB operations
5. **Employee**: Reviews decision and finalizes (approve/pend/deny)

## Data Storage
Claims data stored in Cosmos DB collections:
- `claims`, `artifacts`, `extractions_files`, `extractions_summary`
- `rules_eval`, `agent_runs`, `events`, `threads`

## Implementation Status
- ✅ Directory structure created
- ⏳ Cosmos DB collections setup
- ⏳ Agent implementation
- ⏳ Dashboard development
