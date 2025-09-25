"""
Base Insurance Agent Class
Provides common functionality for all insurance agents including MCP and A2A protocols
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import aiohttp
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.prompt_template.input_variable import InputVariable
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from shared.mcp_config import MCPConfig, A2A_AGENT_PORTS, LOGGING_CONFIG

class BaseInsuranceAgent:
    """Base class for all insurance agents with MCP and A2A capabilities"""
    
    def __init__(self, agent_name: str, agent_description: str, port: int):
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.port = port
        self.kernel = None
        self.mcp_servers = []
        self.logger = self._setup_logging()
        self.session = None
        
    def _setup_logging(self) -> logging.Logger:
        """Setup colored logging for the agent"""
        logger = logging.getLogger(f"InsuranceAgent.{self.agent_name}")
        
        # Create colored formatter
        formatter = logging.Formatter(
            f"🏥 [{self.agent_name.upper()}] %(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S"
        )
        
        # Setup console handler
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        return logger
    
    async def initialize(self):
        """Initialize the agent with Semantic Kernel and MCP connections"""
        self.logger.info(f"🚀 Initializing {self.agent_name} agent...")
        
        # Initialize Semantic Kernel
        self.kernel = Kernel()
        
        # Add OpenAI service (you'll need to configure this with your API key)
        # self.kernel.add_service(OpenAIChatCompletion(
        #     ai_model_id="gpt-4",
        #     api_key="your-openai-key"
        # ))
        
        # Initialize MCP connections
        await self._setup_mcp_connections()
        
        # Initialize HTTP session for A2A communication
        self.session = aiohttp.ClientSession()
        
        self.logger.info(f"✅ {self.agent_name} agent initialized successfully")
    
    async def _setup_mcp_connections(self):
        """Setup connections to required MCP servers"""
        server_names = MCPConfig.get_agent_mcp_servers(self.agent_name)
        
        for server_name in server_names:
            server_url = MCPConfig.get_mcp_server_url(server_name)
            self.logger.info(f"🔗 Connecting to MCP server: {server_name} at {server_url}")
            # TODO: Implement actual MCP connection logic
            self.mcp_servers.append(server_name)
    
    async def query_cosmos_via_mcp(self, collection: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query Cosmos DB through MCP protocol"""
        self.logger.info(f"📊 Querying {collection} collection via MCP")
        
        # TODO: Implement actual MCP query logic
        # For now, return mock data
        mock_data = [
            {
                "id": "mock_id",
                "collection": collection,
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "mock": True
            }
        ]
        
        self.logger.info(f"📋 Retrieved {len(mock_data)} records from {collection}")
        return mock_data
    
    async def communicate_with_agent(self, target_agent: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """Communicate with another agent via A2A protocol"""
        target_port = A2A_AGENT_PORTS.get(target_agent)
        if not target_port:
            raise ValueError(f"Unknown agent: {target_agent}")
        
        url = f"http://localhost:{target_port}/api/message"
        
        self.logger.info(f"📡 Sending A2A message to {target_agent} at port {target_port}")
        
        try:
            async with self.session.post(url, json=message) as response:
                if response.status == 200:
                    result = await response.json()
                    self.logger.info(f"✅ Received response from {target_agent}")
                    return result
                else:
                    self.logger.error(f"❌ Failed to communicate with {target_agent}: {response.status}")
                    return {"error": f"Communication failed with status {response.status}"}
        except Exception as e:
            self.logger.error(f"❌ A2A communication error with {target_agent}: {str(e)}")
            return {"error": str(e)}
    
    @kernel_function(
        description="Log an event to the events collection",
        name="log_event"
    )
    async def log_event(self, event_type: str, description: str, metadata: Optional[Dict] = None) -> str:
        """Log an event to the events collection via MCP"""
        event_data = {
            "event_type": event_type,
            "description": description,
            "agent": self.agent_name,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        # Query events collection to log the event
        await self.query_cosmos_via_mcp("events", {"insert": event_data})
        
        self.logger.info(f"📝 Logged event: {event_type} - {description}")
        return f"Event logged successfully: {event_type}"
    
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process an incoming request - to be overridden by specific agents"""
        self.logger.info(f"🔄 Processing request: {request.get('type', 'unknown')}")
        
        # Log the request as an event
        await self.log_event(
            "request_received",
            f"Processing {request.get('type', 'unknown')} request",
            {"request_id": request.get('id'), "source": request.get('source')}
        )
        
        # Base implementation - should be overridden
        return {
            "status": "success",
            "message": f"Request processed by {self.agent_name}",
            "agent": self.agent_name,
            "timestamp": datetime.now().isoformat()
        }
    
    async def shutdown(self):
        """Cleanup resources on shutdown"""
        self.logger.info(f"🛑 Shutting down {self.agent_name} agent...")
        
        if self.session:
            await self.session.close()
        
        self.logger.info(f"✅ {self.agent_name} agent shutdown complete")
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status for health checks"""
        return {
            "agent": self.agent_name,
            "description": self.agent_description,
            "status": "running",
            "port": self.port,
            "mcp_servers": self.mcp_servers,
            "timestamp": datetime.now().isoformat()
        }
