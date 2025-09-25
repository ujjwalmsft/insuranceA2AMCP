"""
Voice Agent Executor - Azure AI Foundry Voice Agent Integration
Implements AgentExecutor for voice-based insurance claims assistance.
Uses Azure AI Foundry Voice Agent for real-time voice interactions.
"""

import asyncio
import json
import logging
import time
import uuid
import os
import httpx
from typing import Any, Dict, List, Optional, AsyncGenerator
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import TaskArtifactUpdateEvent, TaskState, TaskStatus, TaskStatusUpdateEvent
from a2a.utils import new_agent_text_message, new_task, new_text_artifact

# Azure AI Foundry imports
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Shared utilities
from shared.mcp_chat_client import enhanced_mcp_chat_client
from shared.cosmos_db_client import get_cosmos_client, query_claims, get_all_claims

# Import shared conversation tracker
from conversation_tracker import conversation_tracker

# Load environment variables
load_dotenv()


class VoiceAgentExecutor(AgentExecutor):
    """
    Voice Agent Executor for insurance claims assistance
    - Uses Azure AI Foundry Voice Agent for voice interactions
    - Integrates with MCP tools for data access
    - Supports real-time voice conversations
    - Maintains conversation state across voice sessions
    """
    
    def __init__(self):
        self.agent_name = "client_live_voice_agent"
        self.agent_description = "Voice-enabled insurance claims assistant with Azure AI Foundry integration"
        self.logger = self._setup_logging()
        
        # Voice session management
        self.active_voice_sessions = {}
        self.voice_conversation_history = {}
        
        # Session-specific thread management (like orchestrator)
        self.session_threads = {}  # Map session IDs to Azure AI threads
        
        # Azure AI Foundry setup for Voice Agent
        self.project_client = None
        self.agents_client = None
        self.azure_voice_agent = None
        self.current_thread = None  # Default thread (will be replaced by session-specific threads)
        self._setup_azure_ai_client()
        
        # Initialize Azure Voice Agent if client is available
        if self.agents_client:
            self.get_or_create_azure_voice_agent()
        
        # MCP client for data access (fallback)
        self.mcp_client = enhanced_mcp_chat_client
        
        # ADDED: Direct Cosmos DB client for primary data access
        self.direct_cosmos_client = None
        self._init_direct_cosmos_client()
        
    def _init_direct_cosmos_client(self):
        """Initialize direct Cosmos DB client for primary data access"""
        try:
            # Import the direct Cosmos DB client using absolute import
            import sys
            import os
            
            # Add the shared directory to the path
            # From agents/client_live_voice_agent to shared: go up 2 levels to insurance_agents, then to shared
            current_dir = os.path.dirname(os.path.abspath(__file__))
            shared_path = os.path.join(current_dir, '..', '..', 'shared')
            shared_path = os.path.normpath(shared_path)
            
            self.logger.info(f"🔍 Looking for shared directory at: {shared_path}")
            
            if os.path.exists(shared_path):
                if shared_path not in sys.path:
                    sys.path.insert(0, shared_path)
                self.logger.info("✅ Added shared directory to Python path")
                
                # Try to import the Cosmos DB client
                try:
                    from cosmos_db_client import get_cosmos_client
                    self.get_cosmos_client = get_cosmos_client
                    self.logger.info("✅ Direct Cosmos DB client setup ready")
                    return
                except ImportError as e:
                    self.logger.warning(f"⚠️ Failed to import cosmos_db_client: {e}")
            else:
                self.logger.warning(f"⚠️ Shared directory not found at: {shared_path}")
                
        except Exception as e:
            self.logger.warning(f"⚠️ Direct Cosmos DB client setup error: {e}")
        
        # If setup failed
        self.logger.warning("⚠️ Direct Cosmos DB client not available - will use MCP fallback only")
        self.get_cosmos_client = None
    
    def _setup_azure_ai_client(self):
        """Setup Azure AI Foundry client for Voice Agent"""
        try:
            # Get Azure AI configuration from environment
            subscription_id = os.environ.get("AZURE_AI_AGENT_SUBSCRIPTION_ID")
            resource_group = os.environ.get("AZURE_AI_AGENT_RESOURCE_GROUP_NAME")
            project_name = os.environ.get("AZURE_AI_AGENT_PROJECT_NAME")
            endpoint = os.environ.get("AZURE_AI_AGENT_ENDPOINT")
            
            if not all([subscription_id, resource_group, project_name, endpoint]):
                missing = []
                if not subscription_id: missing.append("AZURE_AI_AGENT_SUBSCRIPTION_ID")
                if not resource_group: missing.append("AZURE_AI_AGENT_RESOURCE_GROUP_NAME") 
                if not project_name: missing.append("AZURE_AI_AGENT_PROJECT_NAME")
                if not endpoint: missing.append("AZURE_AI_AGENT_ENDPOINT")
                
                self.logger.warning(f"⚠️ Azure AI configuration missing: {', '.join(missing)}")
                self.logger.info("📋 Will use fallback voice processing without Azure AI Foundry")
                return
                
            self.logger.info(f"🔧 Using Azure AI endpoint: {endpoint}")
            self.logger.info(f"🔧 Project: {project_name} in {resource_group}")
            
            # Create project client
            self.project_client = AIProjectClient(
                endpoint=endpoint,
                credential=DefaultAzureCredential(),
                subscription_id=subscription_id,
                resource_group_name=resource_group,
                project_name=project_name
            )
            
            # Use the project client's agents interface
            self.agents_client = self.project_client.agents
            self.logger.info("✅ Azure AI Foundry client initialized for Voice Agent")
            
        except Exception as e:
            self.logger.error(f"❌ Error setting up Azure AI client: {e}")
            self.logger.warning("⚠️ Will continue without Azure AI Foundry - using fallback logic")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup colored logging for the voice agent"""
        logger = logging.getLogger(f"VoiceAgent.{self.agent_name}")
        formatter = logging.Formatter(
            f"🎤 [VOICE-AGENT-EXECUTOR] %(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S"
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        # Suppress verbose Azure client logging
        logging.getLogger("azure").setLevel(logging.WARNING)
        logging.getLogger("azure.core").setLevel(logging.WARNING)
        logging.getLogger("azure.identity").setLevel(logging.WARNING)
        logging.getLogger("azure.ai").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        
        return logger
    
    def get_or_create_azure_voice_agent(self):
        """Get existing Azure AI Voice Agent or create new one for voice interactions"""
        if not self.agents_client:
            self.logger.warning("⚠️ Azure AI client not available - using fallback voice processing")
            return None
            
        try:
            # Check for stored voice agent ID
            stored_agent_id = os.environ.get("AZURE_VOICE_AGENT_ID")
            self.logger.info(f"🔍 Environment check: AZURE_VOICE_AGENT_ID = {stored_agent_id or 'Not Set'}")
            
            if stored_agent_id:
                self.logger.info(f"🔍 Checking for existing voice agent with ID: {stored_agent_id}")
                try:
                    # Try to retrieve the existing voice agent
                    existing_agent = self.agents_client.get_agent(stored_agent_id)
                    if existing_agent:
                        self.logger.info(f"✅ Found existing Azure AI Voice Agent: {existing_agent.name} (ID: {stored_agent_id})")
                        self.azure_voice_agent = existing_agent
                        
                        # Create a new thread for voice sessions
                        self.current_thread = self.agents_client.threads.create()
                        self.logger.info(f"🧵 Created new voice thread: {self.current_thread.id}")
                        
                        return self.azure_voice_agent
                except Exception as e:
                    self.logger.warning(f"⚠️ Could not retrieve stored voice agent {stored_agent_id}: {e}")
                    self.logger.info("🔄 Will create new voice agent")
            
            # Create new Azure AI Voice Agent
            self.logger.info("🎤 Creating new Azure AI Voice Agent...")
            
            # Voice agent configuration with insurance domain expertise
            voice_agent_config = {
                "name": "InsuranceVoiceAssistant",
                "description": "Voice-enabled insurance claims assistant that provides real-time help with claims lookup, document guidance, and insurance explanations",
                "instructions": """You are a helpful voice assistant for insurance claims processing. You can:

1. **Claims Lookup**: Help customers check claim status, find claim details, and track progress
2. **Insurance Definitions**: Explain insurance terms like deductible, premium, coverage types  
3. **Document Guidance**: Help with document upload requirements and claim submission

Key behaviors:
- Speak naturally and clearly for voice interactions
- Be empathetic when discussing claims and accidents
- Provide specific, actionable guidance
- Use the query_insurance_data function to look up real claim data from our direct database
- Keep responses concise but helpful for voice conversations
- Always confirm important details before taking actions

You have access to a direct database query function for real-time insurance data.
""",
                "model": "gpt-4o",  # Use latest model for voice
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "query_insurance_data",
                            "description": "Query insurance database for claims, policy information, and other data using natural language",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Natural language query about insurance claims, policies, or data. For example: 'Find claim IP-01', 'What is the status of claim OP-05', 'List all claims for patient John Doe'"
                                    }
                                },
                                "required": ["query"]
                            }
                        }
                    }
                ]
            }
            
            # Create the voice agent
            self.azure_voice_agent = self.agents_client.create_agent(
                model=voice_agent_config["model"],
                name=voice_agent_config["name"],
                description=voice_agent_config["description"],
                instructions=voice_agent_config["instructions"],
                tools=voice_agent_config["tools"]
            )
            
            self.logger.info(f"✅ Created new Azure AI Voice Agent: {self.azure_voice_agent.name}")
            self.logger.info(f"🆔 Voice Agent ID: {self.azure_voice_agent.id}")
            self.logger.info("💡 Consider setting AZURE_VOICE_AGENT_ID={} in .env for persistence".format(self.azure_voice_agent.id))
            
            # Create a thread for voice conversations
            self.current_thread = self.agents_client.threads.create()
            self.logger.info(f"🧵 Created voice conversation thread: {self.current_thread.id}")
            
            return self.azure_voice_agent
            
        except Exception as e:
            self.logger.error(f"❌ Error creating/retrieving Azure AI Voice Agent: {e}")
            self.logger.warning("⚠️ Will use fallback voice processing")
            import traceback
            traceback.print_exc()
            return None
    
    async def initialize(self):
        """Initialize the voice agent"""
        self.logger.info("🎤 Voice Agent Executor initialized with Azure AI Foundry")
        self.logger.info("📋 Ready for voice interactions with direct Cosmos DB access")
        
        # ADDED: Initialize direct Cosmos DB client first (primary) - EAGERLY
        if self.get_cosmos_client:
            try:
                self.logger.info("🔧 Initializing direct Cosmos DB client...")
                self.direct_cosmos_client = await self.get_cosmos_client()
                self.logger.info("✅ Direct Cosmos DB client initialized successfully - primary data access ready")
            except Exception as e:
                self.logger.warning(f"⚠️ Direct Cosmos DB client initialization failed: {e}")
                self.direct_cosmos_client = None
        else:
            self.logger.warning("⚠️ Direct Cosmos DB client not available")
            self.direct_cosmos_client = None
        
        # ADDED: Initialize MCP client as fallback
        try:
            self.logger.info("🔧 Initializing MCP client as fallback...")
            await self.mcp_client._initialize_mcp_session()
            self.logger.info("✅ MCP client initialized successfully - fallback data access ready")
        except Exception as e:
            self.logger.warning(f"⚠️ MCP client initialization failed: {e}")
            self.logger.info("📋 Will try to initialize on first query")
        
        # Log data access strategy
        if self.direct_cosmos_client:
            self.logger.info("🎯 Data Access Strategy: Direct Cosmos DB (primary) + MCP (fallback)")
        elif self.mcp_client.session_id:
            self.logger.info("🎯 Data Access Strategy: MCP only (direct Cosmos not available)")
        else:
            self.logger.warning("⚠️ No data access methods available at startup")
        
        if self.azure_voice_agent:
            self.logger.info(f"✅ Azure AI Voice Agent ready: {self.azure_voice_agent.name}")
        else:
            self.logger.info("📱 Using fallback voice processing (Azure AI not available)")
    
    def get_or_create_session_thread(self, session_id: str):
        """
        Get existing thread for session or create new one (like orchestrator pattern)
        """
        if not self.agents_client:
            return None
            
        if session_id in self.session_threads:
            existing_thread = self.session_threads[session_id]
            self.logger.debug(f"🧵 Using existing thread for session {session_id}: {existing_thread.id}")
            return existing_thread
        else:
            # Create new thread for this voice session
            new_thread = self.agents_client.threads.create()
            self.session_threads[session_id] = new_thread
            self.logger.info(f"🧵 Created new thread for voice session {session_id}: {new_thread.id}")
            return new_thread
    
    async def execute(self, request_context: RequestContext) -> AsyncGenerator[Any, None]:
        """Execute voice agent request with conversation tracking"""
        import uuid  # Import uuid at the top of the function
        
        self.logger.info("🔄 Voice Agent execute called - Processing voice interaction")
        
        try:
            # Extract request details
            task = request_context.task
            
            # Extract text from our custom Message object
            if hasattr(task, 'parts') and task.parts:
                user_message = task.parts[0].root.text
            elif hasattr(task, 'prompt'):
                user_message = task.prompt
            else:
                user_message = str(task)
                
            session_id = getattr(request_context, 'session_id', str(uuid.uuid4())[:8])
            
            self.logger.info(f"🎙️ Processing voice request: '{user_message}' for session {session_id}")
            
            # Start conversation tracking session if not active
            if not conversation_tracker.current_session_id:
                conversation_tracker.start_session({
                    "agent_type": "client_live_voice_agent",
                    "session_source": "a2a_request",
                    "user_session_id": session_id
                })
            
            # Log the incoming user message
            conversation_tracker.log_voice_interaction(
                transcript=user_message,
                audio_metadata={
                    "session_id": session_id,
                    "request_time": datetime.now().isoformat(),
                    "agent": "client_live_voice_agent"
                }
            )
            
            # Create response task using the request context message
            task = request_context.current_task
            if not task:
                # Instead of using new_task() which expects proper A2A Message objects,
                # create a simple task manually for our voice agent
                
                # Create a minimal task object without using new_task()
                task = type('SimpleTask', (), {
                    'id': str(uuid.uuid4()),
                    'context_id': f"voice-{session_id}",
                    'status': TaskStatus(state=TaskState.submitted),
                    'task_id': str(uuid.uuid4())
                })()
            
            response_task = task
            response_task.status = TaskStatus(state=TaskState.working)
            
            # Process with Azure AI Voice Agent if available
            session_thread = self.get_or_create_session_thread(session_id) if self.azure_voice_agent else None
            self.logger.info(f"🔍 Checking Azure AI availability: agent={bool(self.azure_voice_agent)}, session_thread={bool(session_thread)}")
            if self.azure_voice_agent and session_thread:
                self.logger.info("🤖 Using Azure AI Voice Agent processing path")
                try:
                    response_text = await self._process_with_azure_voice_agent(user_message, session_id)
                    
                    # Only enhance if Azure AI actually worked
                    if response_text and not response_text.startswith("I'm ready to help"):
                        # Enhance Azure AI response with database data if needed
                        self.logger.info("🔍 Attempting to enhance Azure AI response with database data")
                        enhanced_response = await self._enhance_response_with_mcp(user_message, response_text, session_id)
                        response_text = enhanced_response
                        self.logger.info(f"📝 Final enhanced response: {response_text[:100]}...")
                    else:
                        # Azure AI didn't work properly, use fallback directly
                        self.logger.info("📱 Azure AI response insufficient, using Direct Cosmos fallback")
                        response_text = await self._fallback_voice_processing(user_message, session_id)
                except Exception as e:
                    self.logger.error(f"❌ Azure AI processing failed: {e}")
                    self.logger.info("📱 Using Direct Cosmos fallback due to Azure AI failure")
                    response_text = await self._fallback_voice_processing(user_message, session_id)
            else:
                # Fallback processing with Direct Cosmos DB integration
                self.logger.info("📱 Using fallback processing path (no Azure AI)")
                response_text = await self._fallback_voice_processing(user_message, session_id)
            
            # Log the agent response
            conversation_tracker.log_agent_response(
                response=response_text,
                response_metadata={
                    "session_id": session_id,
                    "response_time": datetime.now().isoformat(),
                    "agent": "client_live_voice_agent",
                    "azure_ai_used": bool(self.azure_voice_agent and session_thread),
                    "session_thread_id": session_thread.id if session_thread else None
                }
            )
            
            # Create response artifact
            response_artifact = new_text_artifact(
                name='voice_response',
                description='Voice agent response with database integration',
                text=response_text,
            )
            
            # Update task with response
            response_task.status = TaskStatus(state=TaskState.completed)
            response_task.artifacts = [response_artifact]
            
            # Yield response events
            yield TaskStatusUpdateEvent(
                task_id=response_task.task_id,
                contextId=getattr(request_context.message, 'context_id', f"voice-{session_id}"),
                status=TaskStatus(state=TaskState.completed),
                final=True
            )
            
            yield TaskArtifactUpdateEvent(
                task_id=response_task.task_id,
                contextId=getattr(request_context.message, 'context_id', f"voice-{session_id}"),
                artifact=response_artifact,
                append=False,
                last_chunk=True
            )
            
            self.logger.info(f"✅ Voice interaction completed for session {session_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Error in voice agent execution: {e}")
            import traceback
            traceback.print_exc()
            
            # Log the error event
            conversation_tracker.log_system_event(
                event=f"Error in voice agent execution: {str(e)}",
                event_metadata={
                    "error_type": type(e).__name__,
                    "session_id": session_id if 'session_id' in locals() else "unknown",
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Yield error response
            if 'request_context' in locals() and hasattr(request_context, 'current_task') and request_context.current_task:
                error_task = request_context.current_task
            else:
                # Create minimal error response without new_task to avoid the same error
                yield TaskStatusUpdateEvent(
                    task_id="error_task",
                    contextId=getattr(request_context.message, 'context_id', "voice-error") if 'request_context' in locals() and hasattr(request_context, 'message') else "voice-error",
                    status=TaskStatus(state=TaskState.failed),
                    final=True
                )
                return
            
            error_task.status = TaskStatus(state=TaskState.failed)
            
            yield TaskStatusUpdateEvent(
                task_id=error_task.task_id,
                contextId=getattr(request_context.message, 'context_id', "voice-error"),
                status=TaskStatus(state=TaskState.failed),
                final=True
            )
    
    async def _process_with_azure_voice_agent(self, user_message: str, session_id: str) -> str:
        """Process user message with Azure AI Voice Agent"""
        try:
            self.logger.info(f"🤖 Processing with Azure AI Voice Agent: {user_message[:50]}...")
            
            # Get or create session-specific thread (like orchestrator)
            session_thread = self.get_or_create_session_thread(session_id)
            if not session_thread:
                self.logger.warning("⚠️ No session thread available")
                return ""

            # Use the correct API structure discovered from debugging
            try:
                # Create message using session-specific thread
                message = await self.agents_client.messages.create(
                    thread_id=session_thread.id,
                    role="user",
                    content=user_message
                )
                self.logger.info(f"✅ Message created successfully: {message.id if hasattr(message, 'id') else 'Message sent'}")
                
                # Create and run the agent using session-specific thread
                run = await self.agents_client.runs.create(
                    thread_id=session_thread.id,
                    agent_id=self.azure_voice_agent.id
                )
                self.logger.info(f"✅ Run created successfully: {run.id if hasattr(run, 'id') else 'Run started'}")
                
                # Wait for run completion and handle function calls
                max_wait_time = 60  # 60 seconds timeout
                wait_time = 0
                
                while wait_time < max_wait_time:
                    run_status = await self.agents_client.runs.get(thread_id=session_thread.id, run_id=run.id)
                    self.logger.info(f"🔄 Run status: {run_status.status}")
                    
                    if run_status.status == "completed":
                        self.logger.info("✅ Azure AI run completed successfully")
                        break
                    elif run_status.status == "failed":
                        self.logger.error("❌ Azure AI run failed")
                        break
                    elif run_status.status == "requires_action":
                        # Handle function calls
                        self.logger.info("🔧 Handling function calls...")
                        tool_outputs = []
                        
                        for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
                            function_name = tool_call.function.name
                            function_args = json.loads(tool_call.function.arguments)
                            
                            self.logger.info(f"🔧 Azure AI requesting function: {function_name} with args: {function_args}")
                            
                            if function_name == "query_insurance_data":
                                # Route to our direct Cosmos DB client
                                query = function_args.get("query", "")
                                result = await self._try_direct_cosmos_query(query, session_id)
                                
                                if not result:
                                    # Fallback to MCP if direct Cosmos fails
                                    result = await self._try_mcp_query(query, session_id)
                                
                                if not result:
                                    result = "I apologize, but I couldn't retrieve the information from our database at the moment. Please try again."
                                
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": result
                                })
                            else:
                                self.logger.warning(f"⚠️ Unknown function call: {function_name}")
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": "Function not implemented"
                                })
                        
                        # Submit tool outputs
                        if tool_outputs:
                            run = await self.agents_client.runs.submit_tool_outputs(
                                thread_id=session_thread.id,
                                run_id=run.id,
                                tool_outputs=tool_outputs
                            )
                    
                    import asyncio
                    await asyncio.sleep(1)
                    wait_time += 1
                
                # Get the response from session-specific thread
                messages = await self.agents_client.messages.list(thread_id=session_thread.id)
                if hasattr(messages, 'data') and messages.data:
                    # Get the latest assistant message
                    for msg in reversed(messages.data):
                        if hasattr(msg, 'role') and msg.role == 'assistant':
                            if hasattr(msg, 'content') and msg.content:
                                content = msg.content[0] if isinstance(msg.content, list) else msg.content
                                if hasattr(content, 'text'):
                                    response_text = content.text
                                elif hasattr(content, 'value'):
                                    response_text = content.value
                                else:
                                    response_text = str(content)
                                
                                self.logger.info(f"✅ Azure AI response received: {response_text[:100]}...")
                                return response_text
                
                self.logger.warning("⚠️ No assistant response found in messages")
                return ""
                
            except Exception as api_error:
                self.logger.error(f"❌ Azure AI API error: {api_error}")
                return ""
            
        except Exception as e:
            self.logger.error(f"❌ Error processing with Azure AI Voice Agent: {e}")
            return ""
    
    async def _fallback_voice_processing(self, user_message: str, session_id: str) -> str:
        """Enhanced fallback voice processing with Direct Cosmos DB (primary) and MCP (fallback)"""
        self.logger.info("📱 Using enhanced fallback voice processing with Direct Cosmos DB + MCP")
        
        # PRIMARY: Try direct Cosmos DB operations first
        try:
            self.logger.info("🔍 Attempting direct Cosmos DB query...")
            cosmos_response = await self._try_direct_cosmos_query(user_message, session_id)
            if cosmos_response and len(cosmos_response.strip()) > 20:  # Got meaningful response
                self.logger.info("✅ Direct Cosmos query successful, returning database results")
                return cosmos_response
            else:
                self.logger.warning(f"⚠️ Direct Cosmos query returned insufficient data: '{cosmos_response[:50] if cosmos_response else 'None'}'")
        except Exception as e:
            self.logger.warning(f"⚠️ Direct Cosmos query failed, trying MCP fallback: {e}")
        
        # FALLBACK: Try MCP integration as secondary option
        try:
            self.logger.info("🔍 Attempting MCP query as fallback...")
            mcp_response = await self._try_mcp_query(user_message, session_id)
            if mcp_response and len(mcp_response.strip()) > 20:  # Got meaningful response
                self.logger.info("✅ MCP fallback query successful, returning database results")
                return mcp_response
            else:
                self.logger.warning(f"⚠️ MCP query returned insufficient data: '{mcp_response[:50] if mcp_response else 'None'}'")
        except Exception as e:
            self.logger.warning(f"⚠️ MCP query failed, using pattern matching: {e}")
        
        # LAST RESORT: Pattern matching for common insurance requests
        message_lower = user_message.lower()
        
        if any(word in message_lower for word in ['claim', 'status', 'number']):
            return "I can help you check your claim status. To look up your claim, I'll need your claim number. Can you provide that?"
        
        elif any(word in message_lower for word in ['vehicle', 'car', 'auto', 'toyota', 'honda', 'ford']):
            return "I can help you find vehicle information in our database. What specific vehicle details are you looking for?"
        
        elif any(word in message_lower for word in ['database', 'data', 'available', 'container']):
            return "I can search our insurance database for claims, vehicles, and policy information. What would you like me to look up?"
        
        elif any(word in message_lower for word in ['deductible', 'premium', 'coverage']):
            return "I'd be happy to explain insurance terms. Which specific term would you like me to explain?"
        
        elif any(word in message_lower for word in ['document', 'upload', 'file']):
            return "I can guide you through document submission. What type of documents do you need to submit for your claim?"
        
        elif any(word in message_lower for word in ['help', 'what', 'how']):
            return "I'm here to help with your insurance needs. I can assist with claim lookups, explain insurance terms, and guide you through document submission. What would you like help with?"
        
        else:
            return "I'm your voice assistant for insurance help. I can check claim status, explain insurance terms, and help with documents. How can I assist you today?"

    async def _enhance_response_with_mcp(self, user_message: str, azure_response: str, session_id: str) -> str:
        """Enhance Azure AI response with Direct Cosmos DB (primary) and MCP (fallback) data when relevant"""
        try:
            self.logger.info(f"🔍 _enhance_response_with_mcp called with Azure response: {azure_response[:100]}...")
            
            # Check if the user is asking for specific data that might be in the database
            message_lower = user_message.lower()
            data_keywords = ['claim', 'vehicle', 'database', 'data', 'status', 'find', 'search', 'lookup']
            
            if any(keyword in message_lower for keyword in data_keywords):
                self.logger.info("🔍 User query seems to require database lookup, trying Direct Cosmos first...")
                
                # PRIMARY: Try direct Cosmos DB query
                cosmos_response = await self._try_direct_cosmos_query(user_message, session_id)
                if cosmos_response and len(cosmos_response.strip()) > 20:
                    self.logger.info("✅ Enhanced Azure response with Direct Cosmos data")
                    enhanced = f"{azure_response}\n\nBased on our database search:\n{cosmos_response}"
                    self.logger.info(f"📝 Final enhanced response: {enhanced[:150]}...")
                    return enhanced
                else:
                    self.logger.warning(f"⚠️ Direct Cosmos query returned insufficient data, trying MCP fallback...")
                
                # FALLBACK: Try MCP query
                mcp_response = await self._try_mcp_query(user_message, session_id)
                if mcp_response and len(mcp_response.strip()) > 20:
                    self.logger.info("✅ Enhanced Azure response with MCP fallback data")
                    enhanced = f"{azure_response}\n\nBased on our database search:\n{mcp_response}"
                    self.logger.info(f"📝 Final enhanced response: {enhanced[:150]}...")
                    return enhanced
                else:
                    self.logger.warning(f"⚠️ MCP query also returned insufficient data: '{mcp_response[:50] if mcp_response else 'None'}'")
            else:
                self.logger.info("ℹ️ No database keywords detected, skipping database enhancement")
            
            return azure_response
            
        except Exception as e:
            self.logger.warning(f"⚠️ Could not enhance response with database data: {e}")
            return azure_response

    async def _try_direct_cosmos_query(self, user_message: str, session_id: str) -> str:
        """Try to answer user query using direct Cosmos DB operations (PRIMARY method)"""
        try:
            self.logger.info(f"🔗 Attempting direct Cosmos query for: {user_message[:50]}...")
            
            # Check if direct Cosmos client is available
            if not self.direct_cosmos_client:
                self.logger.warning("⚠️ Direct Cosmos client not available, will fallback to MCP")
                return ""
            
            # Analyze user intent for database operations
            message_lower = user_message.lower()
            
            # Check for specific claim ID queries FIRST (higher priority)
            import re
            # Match both IP-04 and IP04 formats
            claim_pattern = r'((?:IP|OP)-?\d+)'
            match = re.search(claim_pattern, user_message, re.IGNORECASE)
            
            if match:
                claim_id = match.group(1).upper()
                # Normalize to database format (add hyphen if missing)
                if not '-' in claim_id:
                    # Convert IP04 to IP-04, OP03 to OP-03
                    claim_id = claim_id[:2] + '-' + claim_id[2:]
                self.logger.info(f"🔍 Searching for specific claim using direct Cosmos: {claim_id}")
                
                # Search for specific claim using direct Cosmos client
                claims = await self.direct_cosmos_client.search_claims(search_term=claim_id)
                
                if claims:
                    claim = claims[0]
                    response = f"Found claim {claim_id}: Patient {claim.get('patientName', 'Unknown')}, Status: {claim.get('status', 'Unknown')}, Diagnosis: {claim.get('diagnosis', 'No diagnosis')}"
                    
                    # Log the direct Cosmos interaction
                    conversation_tracker.log_system_event(
                        event="Direct Cosmos specific claim query",
                        event_metadata={
                            "query": user_message,
                            "claim_id": claim_id,
                            "session_id": session_id,
                            "found": True,
                            "method": "direct_cosmos",
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                    
                    self.logger.info(f"✅ Direct Cosmos query successful: Found claim {claim_id}")
                    return response
                else:
                    self.logger.info(f"📭 Direct Cosmos query: Claim {claim_id} not found")
                    return f"Claim {claim_id} not found in the database."
            
            # Check for general claims-related queries
            elif any(word in message_lower for word in ['claim', 'claims', 'database', 'data']):
                self.logger.info("🔍 Detected general claims query, fetching from direct Cosmos DB...")
                
                # Get all claims directly from Cosmos using the direct client
                claims = await self.direct_cosmos_client.get_all_claims()
                
                if claims:
                    self.logger.info(f"✅ Direct Cosmos query successful: {len(claims)} claims found")
                    
                    # Format the response
                    response_parts = ["The database contains the following insurance claims:"]
                    
                    for i, claim in enumerate(claims[:10], 1):  # Limit to first 10 for response size
                        claim_id = claim.get('claimId', 'Unknown')
                        patient_name = claim.get('patientName', 'Unknown')
                        status = claim.get('status', 'Unknown')
                        diagnosis = claim.get('diagnosis', 'No diagnosis')
                        
                        response_parts.append(f"{i}. **Claim ID: {claim_id}** - {patient_name}, Status: {status}. Diagnosis: {diagnosis}")
                    
                    if len(claims) > 10:
                        response_parts.append(f"\n...and {len(claims) - 10} more claims in the database.")
                    
                    response = "\n\n".join(response_parts)
                    
                    # Log the direct Cosmos interaction
                    conversation_tracker.log_system_event(
                        event="Direct Cosmos query executed",
                        event_metadata={
                            "query": user_message,
                            "session_id": session_id,
                            "claims_found": len(claims),
                            "response_length": len(response),
                            "method": "direct_cosmos",
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                    
                    return response
                else:
                    self.logger.warning("📭 No claims found in direct Cosmos DB")
                    return "No insurance claims found in the database."
            
            self.logger.info("📭 Query doesn't match known patterns for direct Cosmos operations")
            return ""
                
        except Exception as e:
            self.logger.error(f"❌ Direct Cosmos query failed with exception: {e}")
            import traceback
            self.logger.error(f"📊 Full traceback: {traceback.format_exc()}")
            self.logger.info("🔄 Will fallback to MCP if available")
            return ""

    async def _try_mcp_query(self, user_message: str, session_id: str) -> str:
        """Try to answer user query using MCP tools (FALLBACK method)"""
        try:
            self.logger.info(f"🔗 Attempting MCP fallback query for: {user_message[:50]}...")
            
            if not self.mcp_client:
                self.logger.warning("⚠️ MCP client not available")
                return ""
            
            self.logger.info(f"✅ MCP client available: {type(self.mcp_client)}")
            
            # Use the MCP client to query the database
            self.logger.info("🔍 Calling mcp_client.query_cosmos_data...")
            response = await self.mcp_client.query_cosmos_data(user_message)
            self.logger.info(f"📊 MCP raw response: {response[:200] if response else 'None'}...")
            
            if response:
                self.logger.info(f"✅ MCP fallback query successful: {len(response)} characters returned")
                
                # Log the MCP interaction
                conversation_tracker.log_system_event(
                    event="MCP fallback query executed",
                    event_metadata={
                        "query": user_message,
                        "session_id": session_id,
                        "response_length": len(response),
                        "method": "mcp_fallback",
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
                return response
            else:
                self.logger.info("📭 MCP fallback query returned empty response")
                return ""
                
        except Exception as e:
            self.logger.error(f"❌ MCP query failed with exception: {e}")
            import traceback
            self.logger.error(f"📊 Full traceback: {traceback.format_exc()}")
            return ""

    async def cancel(self, task_id: str) -> None:
        """Cancel a running task - required by AgentExecutor abstract class"""
        self.logger.info(f"🚫 Cancelling voice task: {task_id}")
        
        # Log cancellation event
        conversation_tracker.log_system_event(
            event=f"Task cancelled: {task_id}",
            event_metadata={
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
                "action": "cancel"
            }
        )
        
        # Implementation for task cancellation
        # For voice agents, we might need to stop audio streams or ongoing Azure AI operations
        # For now, implement as placeholder to satisfy abstract class requirement
        pass

    def cleanup(self):
        """Clean up resources when shutting down"""
        self.logger.info("🧹 Cleaning up Voice Agent Executor resources...")
        
        # End current conversation session
        if conversation_tracker.current_session_id:
            conversation_tracker.log_system_event(
                event="Voice agent shutting down",
                event_metadata={
                    "timestamp": datetime.now().isoformat(),
                    "action": "cleanup"
                }
            )
            conversation_tracker.end_session()
        
        # Add cleanup logic for Azure connections, audio resources, etc.
        pass