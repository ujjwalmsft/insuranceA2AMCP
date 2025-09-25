"""
A2A Communication Client for Insurance Agents
Handles agent-to-agent communication using the A2A protocol
"""

import asyncio
import json
import httpx
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from shared.mcp_config import A2A_AGENT_PORTS

class A2AClient:
    """
    Client for A2A (Agent-to-Agent) communication
    Enables agents to communicate with each other using the A2A protocol
    """
    
    def __init__(self, source_agent: str):
        self.source_agent = source_agent
        self.logger = logging.getLogger(f"A2AClient.{source_agent}")
        # Increased timeout for all operations to handle longer processing
        self.default_timeout = 120.0  # 2 minutes for all agents
        # Extended timeout for document processing operations
        self.document_timeout = 180.0  # 3 minutes for document processing
        self.client = httpx.AsyncClient(timeout=self.default_timeout)
    
    def _get_agent_url(self, agent_name: str) -> str:
        """Get the URL for a specific agent"""
        port = A2A_AGENT_PORTS.get(agent_name)
        if not port:
            raise ValueError(f"Unknown agent: {agent_name}")
        return f"http://localhost:{port}"
    
    async def send_request(self, target_agent: str, task: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send an A2A request to another agent
        
        Args:
            target_agent: Name of the target agent
            task: Task description or command
            parameters: Task parameters
            
        Returns:
            Response from the target agent
        """
        try:
            if parameters is None:
                parameters = {}
                
            agent_url = self._get_agent_url(target_agent)
            self.logger.info(f"📤 Sending A2A request to {target_agent} at {agent_url}: {task}")
            
            # Prepare proper A2A request payload using message/send method
            import uuid
            
            # Create the task text with parameters
            task_text = f"Task: {task}"
            if parameters:
                task_text += f". Parameters: {json.dumps(parameters)}"
            
            payload = {
                "jsonrpc": "2.0",
                "id": f"a2a-{target_agent}-{uuid.uuid4()}",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"msg-{uuid.uuid4()}",
                        "role": "user",
                        "parts": [
                            {
                                "kind": "text",
                                "text": task_text
                            }
                        ]
                    },
                    "context_id": f"ctx-{uuid.uuid4()}",
                    "message_id": f"msg-{uuid.uuid4()}"
                }
            }
            
            self.logger.info(f"🔗 Making A2A POST request to: {agent_url}")
            
            # Use extended timeout for document processing operations
            timeout = self.document_timeout if target_agent == "document_intelligence" else self.default_timeout
            
            # Create client with appropriate timeout for this request
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Send request to target agent using correct A2A protocol
                response = await client.post(
                    agent_url,  # No /execute suffix - use root endpoint
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
            
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f"✅ A2A request to {target_agent} completed successfully")
                
                # Extract content from A2A response format
                if "result" in result and result["result"]:
                    # Get the message content from the A2A response
                    messages = result["result"].get("messages", [])
                    if messages:
                        # Get the latest assistant message
                        assistant_message = None
                        for msg in reversed(messages):
                            if msg.get("role") == "assistant":
                                assistant_message = msg
                                break
                        
                        if assistant_message and "parts" in assistant_message:
                            # Extract text from parts
                            content_parts = []
                            for part in assistant_message["parts"]:
                                if part.get("type") == "text":
                                    content_parts.append(part["text"])
                            
                            if content_parts:
                                content_text = "\n".join(content_parts)
                                
                                # Try to parse as JSON if it looks like structured data
                                try:
                                    parsed_content = json.loads(content_text)
                                    return parsed_content
                                except json.JSONDecodeError:
                                    # Return as text if not JSON
                                    return {"content": content_text, "status": "success"}
                
                # Fallback: return the full result if we can't parse it
                return result
            else:
                error_msg = f"A2A request failed: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                return {"error": error_msg, "status": "failed"}
                
        except Exception as e:
            error_msg = f"Error sending A2A request to {target_agent}: {str(e)}"
            self.logger.error(error_msg)
            return {"error": error_msg, "status": "failed"}
    
    async def process_claim_with_clarifier(self, claim_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send claim to Intake Clarifier agent for initial processing
        
        Args:
            claim_data: Claim information to process
            
        Returns:
            Clarified claim data
        """
        return await self.send_request(
            "intake_clarifier",
            "clarify_claim_intake",
            {"claim_data": claim_data}
        )
    
    async def analyze_documents_with_intelligence(self, claim_id: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Send documents to Document Intelligence agent for analysis
        
        Args:
            claim_id: The claim ID
            documents: List of documents to analyze
            
        Returns:
            Document analysis results
        """
        return await self.send_request(
            "document_intelligence",
            "analyze_claim_documents",
            {"claim_id": claim_id, "documents": documents}
        )
    
    async def validate_coverage_with_rules_engine(self, claim_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send claim to Coverage Rules Engine for policy validation
        
        Args:
            claim_data: Claim data to validate
            
        Returns:
            Coverage validation results
        """
        return await self.send_request(
            "coverage_rules_engine",
            "validate_claim_coverage",
            {"claim_data": claim_data}
        )
    
    async def orchestrate_claim_processing(self, claim_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send claim to Claims Orchestrator for complete processing workflow
        
        Args:
            claim_data: Claim data to process
            
        Returns:
            Complete processing results
        """
        return await self.send_request(
            "claims_orchestrator",
            "process_claim_workflow",
            {"claim_data": claim_data}
        )
    
    async def get_agent_status(self, agent_name: str) -> Dict[str, Any]:
        """
        Get the status of another agent
        
        Args:
            agent_name: Name of the agent to check
            
        Returns:
            Agent status information
        """
        try:
            agent_url = self._get_agent_url(agent_name)
            response = await self.client.get(f"{agent_url}/.well-known/agent.json")
            
            if response.status_code == 200:
                return {"status": "online", "info": response.json()}
            else:
                return {"status": "offline", "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"status": "offline", "error": str(e)}
    
    async def broadcast_message(self, message: str, parameters: Dict[str, Any] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Broadcast a message to all other agents
        
        Args:
            message: Message to broadcast
            parameters: Message parameters
            
        Returns:
            Responses from all agents
        """
        results = []
        
        for agent_name in A2A_AGENT_PORTS.keys():
            if agent_name != self.source_agent:
                result = await self.send_request(agent_name, message, parameters)
                results.append({
                    "agent": agent_name,
                    "response": result
                })
        
        return {"broadcast_results": results}
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
