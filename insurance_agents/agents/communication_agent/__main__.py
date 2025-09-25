"""
Communication Agent - A2A Protocol Implementation
Specialized agent for sending email notifications about claim decisions using Azure Communication Services
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
from agents.communication_agent.communication_agent_executor import CommunicationAgentExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reduce Azure SDK logging verbosity
logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
logging.getLogger('azure.identity').setLevel(logging.WARNING)


# Define agent capabilities for Communication Agent
communication_agent_capabilities = AgentCapabilities(streaming=False)

# Define skills
communication_agent_skills = [
    AgentSkill(
        id="send_claim_notification",
        name="Send Claim Notification",
        description="Send email notification about insurance claim decisions using Azure Communication Services",
        tags=["email", "notification", "communication", "claims"],
        parameters_schema={
            "type": "object",
            "properties": {
                "claim_id": {"type": "string", "description": "The claim ID"},
                "status": {"type": "string", "description": "Claim status (approved/denied)"},
                "amount": {"type": "string", "description": "Claim amount"},
                "reason": {"type": "string", "description": "Decision reason"},
                "timestamp": {"type": "string", "description": "Decision timestamp"}
            },
            "required": ["claim_id", "status"]
        }
    ),
    AgentSkill(
        id="health_check",
        name="Email Service Health Check",
        description="Check if email service is available and configured properly",
        tags=["health", "status", "email", "service"],
        parameters_schema={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
]


class A2ACommunicationAgentExecutor:
    """A2A wrapper for Communication Agent executor"""
    
    def __init__(self):
        self.executor = CommunicationAgentExecutor()
        self.logger = logging.getLogger(__name__)
    
    async def execute_skill(self, skill_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a skill using the Communication Agent executor"""
        try:
            self.logger.info(f"📧 Communication Agent executing skill: {skill_name}")
            
            # Map skill names to actions
            if skill_name == "send_claim_notification":
                result = await self.executor.process_request("send_claim_notification", parameters)
            elif skill_name == "health_check":
                result = await self.executor.process_request("health_check", parameters)
            else:
                result = {
                    "success": False,
                    "error": f"Unknown skill: {skill_name}",
                    "timestamp": datetime.now().isoformat()
                }
            
            self.logger.info(f"📧 Communication Agent skill {skill_name} completed: {result.get('success', False)}")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Communication Agent skill execution error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }


def create_communication_agent_app(host: str = "localhost", port: int = 8005):
    """Create the Communication Agent A2A application"""
    
    # Task store and notification setup
    task_store = InMemoryTaskStore()
    push_notification_config_store = InMemoryPushNotificationConfigStore()
    
    # Create httpx client for push notifications
    httpx_client = httpx.AsyncClient()
    push_notification_sender = BasePushNotificationSender(
        httpx_client=httpx_client,
        config_store=push_notification_config_store
    )
    
    # Create executor
    executor = A2ACommunicationAgentExecutor()
    
    # Create agent card
    agent_card = AgentCard(
        name="CommunicationAgent",
        description="Sends email notifications for insurance claim decisions using Azure Communication Services",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=communication_agent_capabilities,
        skills=communication_agent_skills
    )
    
    # Create request handler
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
        push_config_store=push_notification_config_store,
        push_sender=push_notification_sender
    )
    
    # Create A2A application
    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )
    
    # Get the underlying Starlette app and add custom routes
    starlette_app = app.build()
    
    # Add custom /process endpoint for orchestrator compatibility
    from starlette.responses import JSONResponse
    from starlette.requests import Request
    from starlette.routing import Route
    
    async def process_endpoint(request: Request):
        """Custom endpoint for orchestrator compatibility"""
        try:
            logger.info("📧 /process endpoint called by orchestrator")
            
            # Parse request data
            request_data = await request.json()
            action = request_data.get("action")
            data = request_data.get("data", {})
            
            logger.info(f"📧 Processing action: {action} with data: {data}")
            
            # Execute the skill through the executor
            if action == "send_claim_notification":
                result = await executor.execute_skill("send_claim_notification", data)
            elif action == "health_check":
                result = await executor.execute_skill("health_check", data)
            else:
                result = {
                    "success": False,
                    "error": f"Unknown action: {action}",
                    "timestamp": datetime.now().isoformat()
                }
            
            logger.info(f"📧 /process endpoint result: {result}")
            return JSONResponse(content=result)
            
        except Exception as e:
            logger.error(f"❌ /process endpoint error: {e}")
            return JSONResponse(
                content={
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                },
                status_code=500
            )
    
    # Add the route to the existing routes
    process_route = Route("/process", process_endpoint, methods=["POST"])
    starlette_app.router.routes.append(process_route)
    
    logger.info("📧 Communication Agent A2A application created successfully")
    logger.info("📧 Added /process endpoint for orchestrator compatibility")
    
    # Return a simple wrapper that has the build method
    class AppWrapper:
        def __init__(self, app):
            self._app = app
        
        def build(self):
            return self._app
    
    return AppWrapper(starlette_app)


@click.command()
@click.option('--port', default=A2A_AGENT_PORTS.get("communication_agent", 8005), help='Port to run the Communication Agent server')
@click.option('--host', default='localhost', help='Host to bind the server')
def main(port: int, host: str):
    """Run the Communication Agent server"""
    try:
        load_dotenv()
        
        logger.info(f"🚀 Starting Communication Agent on {host}:{port}")
        
        # Create the application
        app = create_communication_agent_app(host, port)
        
        # Run the server
        import uvicorn
        uvicorn.run(app.build(), host=host, port=port, log_level="info")
        
    except Exception as e:
        logger.error(f"❌ Failed to start Communication Agent: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()