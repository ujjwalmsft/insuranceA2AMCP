# Insurance Claims Processing System - Developer Documentation

## 🏗️ Project Overview

This is an **AI-powered insurance claims processing demo system** built with modern agent-based architecture, using Azure AI Foundry, A2A (Agent-to-Agent) protocol, and MCP (Model Context Protocol) for intelligent automation of insurance workflows.

### Core Technologies
- **A2A Protocol**: Agent-to-Agent communication framework
- **MCP Protocol**: Model Context Protocol for database interactions
- **Azure AI Foundry**: AI agent creation and management
- **Azure Cosmos DB**: Primary data storage
- **Semantic Kernel**: Agent orchestration framework
- **FastAPI**: Web services and APIs
- **Voice Live API**: Voice live api with VAD and barge-in support

---

## 📁 Project Structure & File Details

### 🏠 Root Level Files
| File | Purpose | Usage |
|------|---------|-------|
| `.gitignore` | Git ignore rules for Python projects | Excludes Python cache, virtual environments, and sensitive configuration files |

### 🤖 Agents Directory (`insurance_agents/`)

The core of the system - contains all intelligent agents that process insurance claims.

#### Main Configuration
| File | Purpose | Details |
|------|---------|---------|
| `README.md` | Agent architecture overview | Documents the entire agent workflow, data storage structure, and implementation status |

### Install dependencies
- pip install -r req.txt (dependencies without version)
- pip install -r requirements.txt (dependencies with version)

#### 🎯 Claims Orchestrator (`agents/claims_orchestrator/`)
**The brain of the system** - intelligent routing and orchestration agent.

| File | Purpose | What It Does |
|------|---------|--------------|
| `__main__.py` | Entry point for orchestrator agent | Sets up A2A server, initializes Azure AI client, starts background agent discovery |
| `intelligent_orchestrator_executor.py` | Core orchestration logic (4078 lines) | Uses Azure AI Foundry to dynamically route requests, manages agent discovery, handles chat conversations and claim processing workflows |


#### 📋 Intake Clarifier (`agents/intake_clarifier/`)
**Data validation specialist** - ensures claim data integrity.

| File | Purpose | What It Does |
|------|---------|--------------|
| `__main__.py` | Agent startup script | Initializes the intake clarifier agent with A2A protocol |
| `intake_clarifier_executor.py` | Verification logic | Compares claim_details vs extracted_patient_data to identify inconsistencies |
| `a2a_wrapper.py` | A2A protocol wrapper | Handles agent-to-agent communication for intake operations |

#### 📄 Document Intelligence Agent (`agents/document_intelligence_agent/`)
**Document processing expert** - extracts structured data from claim documents.

| File | Purpose | What It Does |
|------|---------|--------------|
| `__main__.py` | Agent entry point | Starts document intelligence processing agent |
| `document_intelligence_executor.py` | Document processing engine | Uses Azure Document Intelligence to extract data from PDFs, creates structured records in Cosmos DB |

#### 🛡️ Coverage Rules Engine (`agents/coverage_rules_engine/`)
**Policy evaluation specialist** - determines coverage and benefits.

| File | Purpose | What It Does |
|------|---------|--------------|
| `__main__.py` | Rules engine startup | Initializes coverage evaluation agent |
| `coverage_rules_executor.py` | Coverage evaluation logic | Uses LLM classification to evaluate claims against policy rules, calculates benefits and deductibles |

#### 📧 Communication Agent (`agents/communication_agent/`)
**Notification specialist** - handles external communications.

| File | Purpose | What It Does |
|------|---------|--------------|
| `__main__.py` | Communication agent startup | Starts notification and communication services |
| `communication_agent_executor.py` | Email/SMS logic | Sends notifications using Azure Communication Services for claim decisions |

### 🌐 Dashboard (`insurance_agents_registry_dashboard/`)
**Professional web interface** for claim processing employees.

| File | Purpose | What It Does |
|------|---------|--------------|
| `app.py` | Unified dashboard server (1911 lines) | Provides both claims processing interface and agent registry management |
| `custom_agents.json` | Agent configuration | Defines available agents, their capabilities, and endpoint URLs |
| `static/agent_registry.html` | Agent management UI | Frontend for managing and monitoring agent status |
| `static/claims_dashboard.html` | Claims processing UI | Employee interface for reviewing and processing claims |
| `static/chat_styles.css` | Dashboard styling | CSS styles for professional dashboard appearance |
| `workflow_logs/` | Workflow tracking | Stores real-time workflow execution logs |

### 🔧 Shared Infrastructure (`shared/`)
**Common utilities and services** used by all agents.

| File | Purpose | What It Does |
|------|---------|--------------|
| `base_agent.py` | Base agent class | Provides common functionality for MCP and A2A protocols, logging, kernel setup |
| `mcp_config.py` | MCP configuration | Defines Cosmos DB connections, agent mappings, and collection schemas |
| `cosmos_db_client.py` | Direct database access | Provides Cosmos DB operations without MCP layer for write operations |
| `cosmos_schema_adapter.py` | Database schema management | Handles schema mapping and data structure validation |
| `agent_discovery.py` | Dynamic agent discovery | Discovers available agents, manages capabilities, handles routing decisions |
| `a2a_client.py` | A2A communication client | Enables agents to communicate using A2A protocol with timeout management |
| `mcp_chat_client.py` | MCP communication layer | Enhanced MCP client for database operations and tool integration |
| `dynamic_workflow_logger.py` | Real-time workflow tracking | Tracks workflow steps, provides API endpoints for frontend consumption |

### 🗄️ Azure Cosmos MCP Server (`azure-cosmos-mcp-server/`)
**Database bridge** - provides MCP interface to Cosmos DB.

| File | Purpose | What It Does |
|------|---------|--------------|
| `python/cosmos_server.py` | MCP server implementation | FastMCP server that provides tools for querying and exploring Cosmos DB containers |
| `python/requirements.txt` | MCP server dependencies | Azure Cosmos, pandas, MCP SDK, and authentication libraries |
| `dataset/claims.json` | Sample claims data | Sample insurance claims for testing (Inpatient/Outpatient claims with documents) |

### 📊 Workflow Logs (`workflow_logs/`, `insurance_agents/workflow_logs/`)
**Execution tracking** - monitors system operations in real-time.

| File | Purpose | What It Does |
|------|---------|--------------|
| `current_workflow_steps.json` | Active workflow tracking | Real-time tracking of claim processing steps with status and timing |
| `workflow_steps.json` | Historical workflow data | Archive of completed workflow executions |

---
## For second usecase (with external customer)
#### 🎤 Client Live Voice Agent (`agents/client_live_voice_agent/`)
**Customer-facing voice interface** for real-time claim submissions.

| File | Purpose | What It Does |
|------|---------|--------------|
| `fastapi_server.py` | FastAPI server with WebSocket support | Provides A2A endpoints and WebSocket connections for Azure Voice Live API integration |
| `voice_agent_executor.py` | Voice agent logic | Implements voice-based insurance assistance using Azure AI Foundry Voice Agent |
| `voice_websocket_handler.py` | WebSocket message handling | Manages real-time voice communication sessions |
| `conversation_tracker.py` | Session state management | Tracks conversation context and state across voice sessions |
| `config/` | Voice agent configuration | Contains voice-specific settings and Azure configurations |
| `routes/` | API route handlers | Defines REST endpoints for voice agent operations |
| `services/` | Business logic services | Contains core voice processing business logic |
| `static/` | Static web assets | Frontend files for voice interface containing HTML, JS files handling VAD|
| `utils/` | Helper utilities | Common utilities for voice processing |

#### 🎙️ Voice Client Frontend (`static/claims_voice_client.js`)
**Advanced Voice Activity Detection & Voice Live API Integration**

The `ClaimsVoiceLiveClient` is a sophisticated JavaScript class that implements real-time voice interaction capabilities for insurance claims processing. It leverages Azure's Voice Live API with advanced voice activity detection (VAD) and intelligent barge-in functionality.

**🎤 Voice Activity Detection (VAD) System:**
- **Detection Type**: `azure_semantic_vad` for semantic understanding of speech patterns
- **Threshold**: `0.4` - Balanced sensitivity for natural conversation flow
- **Prefix Padding**: `300ms` - Captures speech start context  
- **Silence Duration**: `300ms` - Determines end-of-utterance timing
- **Filler Word Removal**: Automatically filters out "um", "ah", etc.
- **Smart Barge-in**: Implements cooldown system (`1200ms`) to prevent false interruptions and uses scheduled audio source tracking to detect when AI is actively speaking

**🌐 Voice Live API Integration:**
- **WebSocket Connection**: Secure connections to Azure's Voice Live API endpoints with automatic reconnection
- **Audio Processing Pipeline**: 24kHz sample rate capture with noise suppression, echo cancellation, and auto-gain control
- **Real-time Streaming**: Uses AudioWorklet for low-latency audio processing, streams PCM data as base64-encoded chunks and then gets converted into int16 format using audio-processor.js
- **Output Rendering**: Receives audio deltas from API, buffers them intelligently, and schedules seamless playback using Web Audio API

**🔄 Advanced Audio Management:**
- **Buffering Strategy**: Intelligent audio chunk buffering that accumulates multiple audio deltas before processing to ensure smooth playback
- **Scheduling System**: Uses precise audio scheduling with `AudioContext.currentTime` to maintain seamless playback continuity
- **Interruption Handling**: When user speech is detected, immediately stops all scheduled audio sources, clears buffered chunks, sends response cancellation to server, and resets playback timing
---
## 🔄 System Architecture & Data Flow

### 1. **Entry Points**
- **Customer Voice Interface**: `client_live_voice_agent/fastapi_server.py` (WebSocket + Voice API)
- **Employee Dashboard**: `insurance_agents_registry_dashboard/app.py` (Web UI)
- **Direct Agent Communication**: Each agent's `__main__.py` (A2A Protocol)

### 2. **Core Processing Flow**
```
Customer/Employee Request 
    ↓
Claims Orchestrator (intelligent routing)
    ↓
Specialist Agents (parallel processing)
    ├── Intake Clarifier (validation)
    ├── Document Intelligence (extraction)  
    ├── Coverage Rules Engine (evaluation)
    └── Communication Agent (notifications)
    ↓
Cosmos DB (data storage)
    ↓
Dashboard (results display)
```

### 3. **Communication Layers**
- **A2A Protocol**: Agent-to-agent communication
- **MCP Protocol**: Database operations via `cosmos_server.py`
- **WebSocket**: Real-time voice communication
- **REST API**: Dashboard and external integrations

### 4. Data Collections 

**Coverage rules are embedded in the instructions of coverage rules engine agent**
**COSMOS DB:**
- *claim_details*: Main claim records with patient and provider information
- *extracted_patient_data*: Details from the document intelligence results.

**BLOB STORAGE:**
This has pdf documents for the inpatient and outpatient. For samples refer to Database Samples directory

### 5. **Azure AI Integration**
- **Azure AI Foundry**: Intelligent agent orchestration and routing
- **Azure Document Intelligence**: PDF and document processing
- **Azure Communication Services**: Email
- **Azure Voice Live API**: Real-time voice interactions

---

## 🚀 Getting Started

### 2. Environment Configuration Setup

The project uses multiple `.env` files for different components. **Quick setup**: Copy all `.env.example` files to `.env` and update with your credentials.

```bash
# Quick setup - Copy all environment files at once
cp .env.example .env
cp insurance_agents\.env.example insurance_agents\.env
cp insurance_agents\agents\claims_orchestrator\.env.example insurance_agents\agents\claims_orchestrator\.env
cp azure-cosmos-mcp-server\python\.env.example azure-cosmos-mcp-server\python\.env
```

#### Detailed Setup for Each Component:

#### 🏗️ Main Project Configuration
```bash
# Root directory - Overall system configuration
cd insurance
cp .env.example .env
```
**Edit `.env` with:**
- Cosmos DB endpoint and primary key
- MCP server and agent port configurations
- Dashboard port settings

#### 🤖 Insurance Agents Configuration  
```bash
# Insurance agents directory - Agent-specific settings
cd insurance_agents
cp .env.example .env
```
**Edit `insurance_agents\.env` with:**
- Cosmos DB connection settings for claims processing
- MCP server configuration
- Logging preferences
- Optional Azure Identity settings

#### 🧠 Claims Orchestrator Configuration
```bash
# Claims orchestrator agent - Azure AI Foundry settings
cd insurance_agents\agents\claims_orchestrator
cp .env.example .env
```
**Edit `claims_orchestrator\.env` with:**
- Azure AI Foundry workspace details
- Agent deployment configurations
- AI model settings

#### 🌐 Cosmos MCP Server Configuration
```bash
# Azure Cosmos MCP server - Database connectivity
cd azure-cosmos-mcp-server\python
cp .env.example .env
```
**Edit `azure-cosmos-mcp-server\python\.env` with:**
- Cosmos DB URI and access key
- MCP server host and port settings
- Optional managed identity configuration

### 3. Configure Azure Services

Create the following Azure resources and update your `.env` file:

#### Required Azure Resources:
- **Azure AI Foundry Workspace** (for agent orchestration)
- **Azure Cosmos DB Account** (for claims data storage)
- **Azure OpenAI Service** (for AI model deployment)
- **Azure Document Intelligence** (for PDF processing)
- **Azure Communication Services** (for notifications)
- **Azure Voice Live API** (for real-time voice interactions)

```env
# Azure AI Foundry Configuration (preferably create in eastus2 location)
AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME=gpt-4o
AZURE_AI_AGENT_ENDPOINT=https://your-region.api.azureml.ms/agents/v1.0/subscriptions/{subscription-id}/resourceGroups/{resource-group}/providers/Microsoft.MachineLearningServices/workspaces/{workspace-name}
AZURE_AI_AGENT_SUBSCRIPTION_ID=your-subscription-id
AZURE_AI_AGENT_RESOURCE_GROUP_NAME=your-resource-group-name
AZURE_AI_AGENT_PROJECT_NAME=your-ai-foundry-project-name
AZURE_AI_AGENT_ID=your-agent-id

# Azure Cosmos DB Configuration
COSMOS_ENDPOINT=https://your-cosmos-account.documents.azure.com:443/
COSMOS_KEY=your-cosmos-primary-key
COSMOS_DATABASE=insurance
COSMOS_CONTAINER=claim_details

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-openai-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Azure Document Intelligence Configuration
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-doc-intel-resource.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=your-document-intelligence-key

# Azure Communication Services Configuration
AZURE_COMMUNICATION_CONNECTION_STRING=endpoint=https://your-communication-resource.communication.azure.com/;accesskey=your-access-key
AZURE_COMMUNICATION_SENDER_EMAIL=DoNotReply@your-domain.azurecomm.net

# Azure Voice Live API Configuration
AZURE_VOICE_LIVE_ENDPOINT=https://your-voice-resource.cognitiveservices.azure.com/
AZURE_VOICE_LIVE_API_KEY=your-voice-api-key
AZURE_VOICE_LIVE_MODEL=gpt-4o-realtime-preview

# MCP Server Configuration
MCP_SERVER_HOST=localhost
MCP_SERVER_PORT=8080

# Agent Ports Configuration
A2A_CLAIMS_ORCHESTRATOR_PORT=8001
A2A_INTAKE_CLARIFIER_PORT=8002
A2A_DOCUMENT_INTELLIGENCE_PORT=8003
A2A_COVERAGE_RULES_ENGINE_PORT=8004
A2A_COMMUNICATION_AGENT_PORT=8005
VOICE_LIVE_AGENT_PORT=8007

# Dashboard Configuration
DASHBOARD_PORT=3000
```
---

## 🔧 Development Guidelines

### Adding New Agents
1. Create agent directory under `agents/`
2. Implement `AgentExecutor` class (see `base_agent.py`)
3. Add entry point `__main__.py`, `__init.py` for package identification
4. Register in `mcp_config.py` and `agent_discovery.py`
5. Update dashboard configuration

### Modifying Workflows
1. Update `intelligent_orchestrator_executor.py` for routing logic
2. Modify `dynamic_workflow_logger.py` for new step types
3. Update dashboard UI for new workflow states

### Database Schema Changes
1. Use `cosmos_schema_adapter.py` to populate collections in cosmosDB and refer to data samples.
2. Modify `mcp_config.py` for collection mappings
3. Update `cosmos_server.py` if new MCP tools needed

---