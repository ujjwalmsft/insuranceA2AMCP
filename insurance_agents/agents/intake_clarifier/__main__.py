"""
Intake Clarifier Agent - A2A Protocol Implementation
Specialized agent for clarifying and validating incoming claims
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import logging
import click
import httpx
from typing import Dict, Any
from datetime import datetime

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, InMemoryPushNotificationConfigStore, BasePushNotificationSender
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv

from shared.mcp_config import A2A_AGENT_PORTS
from agents.intake_clarifier.a2a_wrapper import A2AIntakeClarifierExecutor

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

# Apply custom filter to uvicorn access logger
uvicorn_access_logger = logging.getLogger('uvicorn.access')
uvicorn_access_logger.addFilter(AgentJsonFilter())

# Reduce other logging
logging.getLogger('uvicorn').setLevel(logging.WARNING)
logging.getLogger('a2a.server.apps.jsonrpc.jsonrpc_app').setLevel(logging.ERROR)

load_dotenv()

@click.command()
@click.option('--host', default='localhost')
@click.option('--port', default=A2A_AGENT_PORTS["intake_clarifier"])
def main(host, port):
    """Starts the Intake Clarifier Agent server using A2A."""
    
    # Initialize with proper logging
    logger.info("📝 Intake Clarifier Agent initialized")
    logger.info(f"🔧 Agent skills: ['Claims Validation & Clarification', 'Fraud Risk Assessment']")
    logger.info(f"🌐 Starting server on http://{host}:{port}")
    
    httpx_client = httpx.AsyncClient()
    push_config_store = InMemoryPushNotificationConfigStore()
    request_handler = DefaultRequestHandler(
        agent_executor=A2AIntakeClarifierExecutor(),
        task_store=InMemoryTaskStore(),
        push_config_store=push_config_store,
        push_sender=BasePushNotificationSender(httpx_client, push_config_store),
    )

    server = A2AStarletteApplication(
        agent_card=get_agent_card(host, port), http_handler=request_handler
    )
    
    logger.info("✅ Enhanced Intake Clarifier with fraud detection ready!")
    
    import uvicorn
    uvicorn.run(server.build(), host=host, port=port)

def get_agent_card(host: str, port: int):
    """Returns the Agent Card for the Intake Clarifier Agent."""

    # Build the agent card
    capabilities = AgentCapabilities(streaming=True)
    
    skill_claim_validation = AgentSkill(
        id='claim_validation',
        name='Claims Validation & Clarification',
        description=(
            'Validates and clarifies incoming insurance claims, performs completeness checks, '
            'fraud risk assessment, and generates clarification questions for incomplete claims.'
        ),
        tags=['insurance', 'validation', 'fraud-detection', 'clarification', 'intake'],
        examples=[
            'Validate completeness of auto insurance claim',
            'Assess fraud risk for health insurance claim',
            'Generate clarification questions for incomplete claim',
            'Check customer information validity'
        ],
    )

    skill_fraud_assessment = AgentSkill(
        id='fraud_assessment',
        name='Fraud Risk Assessment',
        description=(
            'Performs initial fraud detection screening using pattern analysis, '
            'historical data comparison, and risk scoring algorithms.'
        ),
        tags=['fraud-detection', 'risk-assessment', 'security', 'analysis'],
        examples=[
            'Calculate fraud risk score for new claim',
            'Identify suspicious claim patterns',
            'Validate claim consistency and authenticity',
            'Flag high-risk claims for manual review'
        ],
    )

    agent_card = AgentCard(
        name='IntakeClarifierAgent',
        description=(
            'Specialized agent for validating and clarifying incoming insurance claims. '
            'Performs completeness checks, fraud risk assessment, and generates '
            'clarification questions to ensure accurate claim processing.'
        ),
        url=f'http://{host}:{port}/',
        version='1.0.0',
        defaultInputModes=['text'],
        defaultOutputModes=['text'],
        capabilities=capabilities,
        skills=[skill_claim_validation, skill_fraud_assessment],
    )

    return agent_card

if __name__ == '__main__':
    main()
