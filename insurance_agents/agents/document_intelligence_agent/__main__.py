"""
Document Intelligence Agent - A2A Protocol Implementation
Specialized agent for document analysis and intelligence extraction
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import asyncio
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

from agents.document_intelligence_agent.document_intelligence_executor import DocumentIntelligenceExecutor
from shared.mcp_config import A2A_AGENT_PORTS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress Azure SDK verbose logging
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
@click.option('--port', default=A2A_AGENT_PORTS["document_intelligence"])
def main(host, port):
    """Starts the Document Intelligence Agent server using A2A."""
    httpx_client = httpx.AsyncClient()
    push_config_store = InMemoryPushNotificationConfigStore()
    request_handler = DefaultRequestHandler(
        agent_executor=DocumentIntelligenceExecutor(),
        task_store=InMemoryTaskStore(),
        push_config_store=push_config_store,
        push_sender=BasePushNotificationSender(httpx_client, push_config_store),
    )

    server = A2AStarletteApplication(
        agent_card=get_agent_card(host, port), http_handler=request_handler
    )
    import uvicorn

    uvicorn.run(server.build(), host=host, port=port)

def get_agent_card(host: str, port: int):
    """Returns the Agent Card for the Document Intelligence Agent."""

    # Build the agent card
    capabilities = AgentCapabilities(streaming=True)
    
    # Define agent skills
    skills = [
        AgentSkill(
            id="document_analysis",
            name="Document Analysis",
            description="Analyze and extract information from insurance documents",
            tags=["document", "analysis", "extraction"]
        ),
        AgentSkill(
            id="text_extraction",
            name="Text Extraction", 
            description="Extract text and data from documents using OCR and NLP",
            tags=["ocr", "text", "extraction"]
        ),
        AgentSkill(
            id="damage_assessment",
            name="Damage Assessment",
            description="Assess damage from images and documents", 
            tags=["damage", "assessment", "images"]
        ),
        AgentSkill(
            id="form_recognition",
            name="Form Recognition",
            description="Recognize and extract data from insurance forms",
            tags=["form", "recognition", "extraction"]
        )
    ]
    
    agent_card = AgentCard(
        name="Document Intelligence Agent",
        description="Specialized agent for analyzing insurance documents, extracting data, and assessing damage",
        version="1.0.0",
        url=f"http://{host}:{port}",
        skills=skills,
        capabilities=capabilities,
        default_input_modes=["text"],
        default_output_modes=["text"]
    )
    
    logger.info("� Document Intelligence Agent initialized")
    logger.info(f"� Agent skills: {[skill.name for skill in agent_card.skills]}")
    
    return agent_card

if __name__ == "__main__":
    main()
