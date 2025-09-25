"""
Intelligent Claims Orchestrator Agent - Azure AI Powered
Main orchestration agent that uses Azure AI Foundry for intelligent routing
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import asyncio
import logging
import click
from typing import Dict, Any
from datetime import datetime

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, InMemoryPushNotificationConfigStore, BasePushNotificationSender
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv

from shared.mcp_config import A2A_AGENT_PORTS
from agents.claims_orchestrator.intelligent_orchestrator_executor import IntelligentClaimsOrchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reduce Azure SDK logging verbosity
logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
logging.getLogger('azure.identity').setLevel(logging.WARNING)

# Custom filter to hide specific agent.json requests
class AgentJsonFilter(logging.Filter):
    def filter(self, record):
        # Filter out agent.json GET requests
        if hasattr(record, 'getMessage'):
            message = record.getMessage()
            if '/.well-known/agent.json' in message and 'GET' in message:
                return False
        return True

# Reduce other logging
logging.getLogger('uvicorn').setLevel(logging.WARNING)
logging.getLogger('a2a.server.apps.jsonrpc.jsonrpc_app').setLevel(logging.ERROR)

load_dotenv()

async def initialize_intelligent_orchestrator():
    """Initialize the intelligent orchestrator with Azure AI"""
    logger.info("🧠 Initializing Intelligent Claims Orchestrator...")
    
    # Create orchestrator instance
    orchestrator = IntelligentClaimsOrchestrator()
    
    try:
        # Initialize agent discovery
        await orchestrator.initialize()
        
        # Get or create Azure AI agent if available
        azure_agent = None
        if orchestrator.agents_client:
            try:
                azure_agent = orchestrator.get_or_create_azure_agent()
                if azure_agent:
                    logger.info("✅ Azure AI agent ready for use!")
                else:
                    logger.warning("⚠️ Azure AI agent setup failed - using fallback mode")
            except Exception as e:
                logger.warning(f"⚠️ Azure AI not available: {str(e)[:100]}...")
                logger.info("🔄 Continuing with fallback routing capabilities")
        else:
            logger.warning("⚠️ Running without Azure AI - using fallback routing")
        
        logger.info(f"🎯 Available agents: {list(orchestrator.available_agents.keys())}")
        return orchestrator
        
    except Exception as e:
        logger.error(f"❌ Error initializing orchestrator: {e}")
        raise

@click.command()
@click.option('--host', default='localhost')
@click.option('--port', default=A2A_AGENT_PORTS["claims_orchestrator"])
def main(host, port):
    """Starts the Intelligent Claims Orchestrator Agent server using A2A + Azure AI."""
    
    # Initialize with proper logging
    logger.info("🧠 Intelligent Claims Orchestrator Agent initialized")
    logger.info(f"🔧 Agent capabilities: AI-powered routing, dynamic workflows, natural conversations")
    logger.info(f"🌐 Starting server on http://{host}:{port}")
    
    # Initialize the orchestrator
    import asyncio
    orchestrator = asyncio.run(initialize_intelligent_orchestrator())
    
    import httpx
    httpx_client = httpx.AsyncClient()
    push_config_store = InMemoryPushNotificationConfigStore()
    request_handler = DefaultRequestHandler(
        agent_executor=orchestrator,  # Use our intelligent orchestrator
        task_store=InMemoryTaskStore(),
        push_config_store=push_config_store,
        push_sender=BasePushNotificationSender(httpx_client, push_config_store),
    )

    server = A2AStarletteApplication(
        agent_card=get_agent_card(host, port), http_handler=request_handler
    )
    
    logger.info("✅ Intelligent Claims Orchestrator with Azure AI ready!")
    logger.info("📊 Workflow API endpoints available at /workflow-steps")
    
    # Apply custom filter to reduce agent.json polling noise
    import logging
    import uvicorn  # Add explicit import
    uvicorn_access_logger = logging.getLogger('uvicorn.access')
    uvicorn_access_logger.addFilter(AgentJsonFilter())
    logger.info("🚀 Starting enhanced orchestrator server...")
    
    # Build the server app
    app = server.build()
    
    # Add CORS middleware to allow frontend connections
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add custom routes for workflow steps using Starlette routing
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    from shared.dynamic_workflow_logger import workflow_logger
    
    # Load existing workflow data on startup
    logger.info("📊 Loading existing workflow data...")
    workflow_logger.load_from_file()
    loaded_workflows = workflow_logger.get_latest_workflows(limit=10)
    logger.info(f"📋 Loaded {len(loaded_workflows)} existing workflow sessions")
    
    async def get_workflow_steps_handler(request):
        """Get workflow steps for a specific session"""
        try:
            session_id = request.path_params['session_id']
            steps = workflow_logger.get_workflow_steps(session_id)
            return JSONResponse({"steps": steps, "session_id": session_id})
        except Exception as e:
            return JSONResponse(
                {"error": str(e), "session_id": session_id}, 
                status_code=500
            )
    
    async def get_latest_workflows_handler(request):
        """Get the most recent workflow sessions"""
        try:
            workflows = workflow_logger.get_latest_workflows(limit=5)
            return JSONResponse({"workflows": workflows})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    
    # Add the routes to the existing app
    app.router.routes.append(Route("/workflow-steps/{session_id}", get_workflow_steps_handler, methods=["GET"]))
    app.router.routes.append(Route("/workflow-steps", get_latest_workflows_handler, methods=["GET"]))
    
    uvicorn.run(app, host=host, port=port, log_level="info")

def get_agent_card(host: str, port: int):
    """Returns the Agent Card for the Claims Orchestrator Agent."""

    # Build the agent card
    capabilities = AgentCapabilities(streaming=True)
    
    skill_claims_orchestration = AgentSkill(
        id='claims_orchestration',
        name='Claims Processing Orchestration',
        description=(
            'AI-powered intelligent orchestrator that dynamically routes insurance requests '
            'to appropriate specialist agents using Azure AI Foundry. Provides natural '
            'language conversations and adaptive workflows without hardcoded processes.'
        ),
        tags=['ai', 'intelligent', 'azure', 'dynamic-routing', 'conversation', 'orchestration'],
        examples=[
            'What are your capabilities?',
            'Help me process a claim with documents',
            'Find information about a specific policy',
            'Route my request to the right specialist',
            'Query our insurance database'
        ],
    )

    skill_ai_routing = AgentSkill(
        id='asst_xvp1TYOJ3EGSyClPD8mDkn2k',
        name='AI-Powered Intelligent Routing',
        description=(
            'Uses Azure AI Foundry to analyze requests and dynamically determine '
            'the best agents to handle each task. Supports natural language conversations '
            'and adaptive workflow orchestration based on context and agent capabilities.'
        ),
        tags=['ai', 'azure', 'routing', 'conversation', 'adaptive', 'intelligence'],
        examples=[
            'Analyze this request and route to the right agent',
            'Have a conversation about insurance operations',
            'Dynamically create workflows based on request type',
            'Use AI to determine the best processing approach'
        ],
    )

    agent_card = AgentCard(
        name='ClaimsOrchestratorAgent',
        description=(
            'Main orchestration agent for insurance claims processing. '
            'Coordinates the entire claims workflow from intake through approval, '
            'managing interactions with specialized agents for validation, '
            'document analysis, and coverage evaluation.'
        ),
        url=f'http://{host}:{port}/',
        version='1.0.0',
        id = 'asst_xvp1TYOJ3EGSyClPD8mDkn2k',
        defaultInputModes=['text'],
        defaultOutputModes=['text'],
        capabilities=capabilities,
        skills=[skill_claims_orchestration, skill_ai_routing],
    )

    return agent_card

if __name__ == '__main__':
    # Get host and port from environment or use defaults
    import os
    HOST = os.getenv('HOST', 'localhost')
    PORT = int(os.getenv('PORT', A2A_AGENT_PORTS["claims_orchestrator"]))
    
    main()
