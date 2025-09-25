#!/usr/bin/env python3
"""
FastAPI Voice Agent Server with A2A Protocol and WebSocket Support
Provides both A2A agent endpoints and WebSocket connections for Voice Live API
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
import json

# Add the parent directory to the path so we can import shared modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
import uvicorn

# A2A Protocol imports
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

# Import voice components (handle both relative and absolute imports)
try:
    from .voice_agent_executor import VoiceAgentExecutor
    from .voice_websocket_handler import voice_websocket_handler
except ImportError:
    from voice_agent_executor import VoiceAgentExecutor
    from voice_websocket_handler import voice_websocket_handler

# Import shared conversation tracker
from conversation_tracker import conversation_tracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='🎤 [VOICE-AGENT-FASTAPI] %(asctime)s - %(levelname)s - %(message)s',
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Suppress verbose Azure client logging
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)
logging.getLogger("azure.ai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

class VoiceFastAPIServer:
    """FastAPI server with A2A protocol support and WebSocket for Voice Live API"""
    
    def __init__(self):
        self.app = FastAPI(
            title="Client Live Voice Agent",
            description="A2A-compliant voice agent with Azure AI Foundry and Voice Live API integration",
            version="1.0.0"
        )
        self.voice_executor = None
        self.agent_card = None
        self.setup_middleware()
        self.setup_routes()
    
    def setup_middleware(self):
        """Setup CORS middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Allow all origins for development
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def setup_routes(self):
        """Setup all routes including A2A endpoints and WebSocket"""
        
        # A2A Protocol endpoints
        @self.app.get("/.well-known/agent.json")
        async def get_agent_card():
            """A2A Agent Card endpoint"""
            if not self.agent_card:
                raise HTTPException(status_code=503, detail="Agent not initialized")
            
            try:
                # Convert AgentCard to dict dynamically
                agent_dict = self.agent_card.model_dump()
                
                # Convert field names from snake_case to camelCase for A2A compatibility
                formatted_dict = {
                    "name": agent_dict.get("name"),
                    "description": agent_dict.get("description"),
                    "url": agent_dict.get("url"),
                    "version": agent_dict.get("version"),
                    "id": "client_live_voice_agent",  # Add id field for A2A compatibility
                    "defaultInputModes": agent_dict.get("default_input_modes", []),
                    "defaultOutputModes": agent_dict.get("default_output_modes", []),
                    "instructions": "Provides voice-based insurance claims assistance with Azure AI Foundry integration and real-time WebSocket communication",
                    "capabilities": agent_dict.get("capabilities", {}),
                    "skills": agent_dict.get("skills", [])
                }
                
                # Convert capabilities if it's an object
                if hasattr(self.agent_card.capabilities, 'model_dump'):
                    formatted_dict["capabilities"] = self.agent_card.capabilities.model_dump()
                
                # Add custom voice capabilities for testing
                if "capabilities" not in formatted_dict:
                    formatted_dict["capabilities"] = {}
                
                formatted_dict["capabilities"]["audio"] = True
                formatted_dict["capabilities"]["voice"] = True
                formatted_dict["capabilities"]["real_time"] = True
                
                # Convert skills if they're objects
                if self.agent_card.skills:
                    formatted_dict["skills"] = [
                        skill.model_dump() if hasattr(skill, 'model_dump') else skill
                        for skill in self.agent_card.skills
                    ]
                
                return JSONResponse(content=formatted_dict)
                
            except Exception as e:
                logger.error(f"Error creating agent card response: {e}")
                # Fallback response
                fallback_dict = {
                    "name": "ClientLiveVoiceAgent",
                    "description": "Voice-enabled insurance claims assistant with real-time interaction",
                    "url": "http://localhost:8007/",
                    "version": "1.0.0",
                    "id": "client_live_voice_agent",
                    "defaultInputModes": ["audio", "text"],
                    "defaultOutputModes": ["audio", "text"],
                    "instructions": "Provides voice-based insurance claims assistance with Azure AI Foundry integration",
                    "capabilities": {
                        "audio": True,
                        "vision": False,
                        "toolUse": True,
                        "contextState": True,
                        "streaming": True
                    },
                    "skills": []
                }
                return JSONResponse(content=fallback_dict)
        
        # Voice interface endpoints
        @self.app.get("/")
        async def serve_voice_interface():
            """Serve the voice client interface"""
            try:
                voice_client_path = Path(__file__).parent / "claims_voice_client.html"
                if voice_client_path.exists():
                    return FileResponse(voice_client_path, media_type="text/html")
                else:
                    return HTMLResponse("""
                    <html>
                    <head><title>Voice Agent</title></head>
                    <body>
                        <h1>Voice Agent Interface</h1>
                        <p>Voice client interface not found. Please ensure voice_client.html exists.</p>
                        <p>Agent Card: <a href="/.well-known/agent.json">/.well-known/agent.json</a></p>
                    </body>
                    </html>
                    """)
            except Exception as e:
                logger.error(f"Error serving voice interface: {e}")
                raise HTTPException(status_code=500, detail="Error serving interface")
        
        @self.app.get("/claims_voice_client.js")
        async def serve_claims_voice_client_js():
            """Serve the claims voice client JavaScript"""
            try:
                js_path = Path(__file__).parent / "claims_voice_client.js"
                if js_path.exists():
                    return FileResponse(js_path, media_type="application/javascript")
                else:
                    raise HTTPException(status_code=404, detail="Claims voice client JavaScript file not found")
            except Exception as e:
                logger.error(f"Error serving claims voice client JavaScript: {e}")
                raise HTTPException(status_code=500, detail="Error serving JavaScript")
        
        @self.app.get("/audio-processor.js")
        async def serve_audio_processor_js():
            """Serve the audio processor JavaScript"""
            try:
                js_path = Path(__file__).parent / "audio-processor.js"
                if js_path.exists():
                    return FileResponse(js_path, media_type="application/javascript")
                else:
                    raise HTTPException(status_code=404, detail="Audio processor JavaScript file not found")
            except Exception as e:
                logger.error(f"Error serving audio processor JavaScript: {e}")
                raise HTTPException(status_code=500, detail="Error serving JavaScript")
        
        @self.app.get("/config.js")
        async def serve_config_js():
            """Serve the configuration JavaScript"""
            try:
                config_path = Path(__file__).parent / "config.js"
                if config_path.exists():
                    return FileResponse(config_path, media_type="application/javascript")
                else:
                    raise HTTPException(status_code=404, detail="Config file not found")
            except Exception as e:
                logger.error(f"Error serving config: {e}")
                raise HTTPException(status_code=500, detail="Error serving config")

        # WebSocket endpoint for Voice Live API conversation tracking
        @self.app.websocket("/ws/voice")
        async def voice_websocket_endpoint(websocket: WebSocket, session_id: str = None):
            """WebSocket endpoint for Voice Live API conversation tracking"""
            logger.info(f"🔌 New WebSocket connection attempt for session: {session_id}")
            
            connection_id = await voice_websocket_handler.connect(websocket, session_id)
            logger.info(f"✅ WebSocket connected: {connection_id}")
            
            try:
                await voice_websocket_handler.handle_voice_message(websocket, connection_id)
            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket disconnected: {connection_id}")
                voice_websocket_handler.disconnect(connection_id)
            except Exception as e:
                logger.error(f"❌ WebSocket error for {connection_id}: {e}")
                voice_websocket_handler.disconnect(connection_id)
        
        # A2A Agent execution endpoint (simplified for WebSocket-based voice)
        @self.app.post("/api/agent/execute")
        async def execute_agent(request: Request):
            """Execute agent request (A2A protocol)"""
            try:
                if not self.voice_executor:
                    return JSONResponse(content={
                        "response": "Voice agent is starting up. Please try again in a moment.",
                        "session_id": "startup",
                        "status": "pending"
                    })
                
                request_data = await request.json()
                user_message = request_data.get("message", "")
                session_id = request_data.get("session_id", "direct_api")
                
                logger.info(f"🎙️ Executing agent request: {user_message[:50]}...")
                
                # Create a proper request context with A2A message structure
                class SimpleRequestContext:
                    def __init__(self, message, session_id):
                        import uuid
                        self.session_id = session_id
                        # Create A2A-compatible message structure with all required attributes
                        text_part = type('TextPart', (), {'text': message})()
                        part_with_root = type('Part', (), {
                            'kind': 'text',
                            'root': text_part  # A2A framework expects 'root' attribute
                        })()
                        
                        self.message = type('Message', (), {
                            'role': 'user',
                            'parts': [part_with_root],
                            'task_id': str(uuid.uuid4()),  # Add required task_id
                            'context_id': f"voice-{session_id}",  # Add context_id
                            'messageId': str(uuid.uuid4())  # Add messageId
                        })()
                        self.task = self.message  # For compatibility
                        self.current_task = None  # Start with no current task
                        
                    def get_user_input(self):
                        return self.message.parts[0].root.text
                
                request_context = SimpleRequestContext(user_message, session_id)
                
                # Execute and collect response
                response_text = ""
                try:
                    async for event in self.voice_executor.execute(request_context):
                        if hasattr(event, 'artifact'):
                            # Check for artifact content in various structures
                            if hasattr(event.artifact, 'content'):
                                response_text = event.artifact.content
                                break
                            elif hasattr(event.artifact, 'text'):
                                response_text = event.artifact.text
                                break
                            elif hasattr(event.artifact, 'parts') and event.artifact.parts:
                                # A2A framework uses parts structure
                                part = event.artifact.parts[0]
                                if hasattr(part, 'text'):
                                    response_text = part.text
                                    break
                                elif hasattr(part, 'content'):
                                    response_text = part.content
                                    break
                                elif hasattr(part, 'root') and hasattr(part.root, 'text'):
                                    response_text = part.root.text
                                    break
                                elif hasattr(part, 'root') and hasattr(part.root, 'content'):
                                    response_text = part.root.content
                                    break
                    
                    # If no response collected, provide fallback
                    if not response_text:
                        response_text = f"I'm ready to help with your voice interactions regarding: {user_message}"
                        
                except Exception as exec_error:
                    logger.warning(f"⚠️ Agent execution had issues: {exec_error}")
                    response_text = f"I understand you're asking about: {user_message}. I'm here to help with your insurance needs."
                
                return JSONResponse(content={
                    "response": response_text,
                    "session_id": session_id,
                    "status": "completed"
                })
                
            except Exception as e:
                logger.error(f"❌ Error executing agent: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Agent execution error",
                        "detail": str(e),
                        "session_id": request_data.get("session_id", "error") if 'request_data' in locals() else "error",
                        "status": "failed"
                    }
                )
        
        # Conversation tracking API endpoints
        @self.app.get("/api/conversation/stats")
        async def get_conversation_stats():
            """Get conversation statistics"""
            try:
                stats = conversation_tracker.get_conversation_stats()
                return JSONResponse(content=stats)
            except Exception as e:
                logger.error(f"Error getting conversation stats: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/conversation/sessions")
        async def get_recent_sessions(limit: int = 10):
            """Get recent conversation sessions"""
            try:
                sessions = conversation_tracker.get_recent_sessions(limit)
                return JSONResponse(content={"sessions": sessions})
            except Exception as e:
                logger.error(f"Error getting recent sessions: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/conversation/session/{session_id}")
        async def get_session_history(session_id: str):
            """Get conversation history for a specific session"""
            try:
                history = conversation_tracker.get_session_history(session_id)
                if history is None:
                    raise HTTPException(status_code=404, detail="Session not found")
                return JSONResponse(content=history)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting session history: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/conversation/search")
        async def search_conversations(query: str, limit: int = 20):
            """Search conversation history"""
            try:
                results = conversation_tracker.search_conversations(query, limit)
                return JSONResponse(content={"results": results})
            except Exception as e:
                logger.error(f"Error searching conversations: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/voice/sessions")
        async def get_active_voice_sessions():
            """Get active voice WebSocket sessions"""
            try:
                sessions = voice_websocket_handler.get_active_sessions()
                return JSONResponse(content={"active_sessions": sessions})
            except Exception as e:
                logger.error(f"Error getting active voice sessions: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # Health check endpoint
        @self.app.get("/api/health")
        async def health_check():
            """Health check endpoint"""
            return JSONResponse(content={
                "status": "healthy",
                "agent_initialized": self.voice_executor is not None,
                "conversation_tracking": True,
                "websocket_support": True,
                "a2a_protocol": True
            })
        
        # ADDED: Startup readiness endpoint to ensure database systems are ready
        @self.app.post("/api/startup/initialize")
        async def initialize_for_chat():
            """Initialize all components for chat readiness (called when 'start chat' button is clicked)"""
            try:
                if not self.voice_executor:
                    return JSONResponse(content={
                        "status": "error",
                        "message": "Voice executor not available",
                        "ready": False
                    })
                
                # Check direct Cosmos DB (primary)
                direct_cosmos_ready = False
                try:
                    if hasattr(self.voice_executor, 'direct_cosmos_client') and self.voice_executor.direct_cosmos_client:
                        logger.info("🔧 Testing direct Cosmos DB connection...")
                        direct_cosmos_ready = await self.voice_executor.direct_cosmos_client.check_connection()
                        if direct_cosmos_ready:
                            logger.info("✅ Direct Cosmos DB ready - primary data access confirmed")
                        else:
                            logger.warning("⚠️ Direct Cosmos DB connection issue")
                except Exception as e:
                    logger.warning(f"⚠️ Direct Cosmos DB test failed: {e}")
                
                # Ensure MCP client is initialized and ready (fallback)
                mcp_ready = False
                try:
                    logger.info("🔧 Ensuring MCP fallback system readiness...")
                    if not self.voice_executor.mcp_client.session_id:
                        await self.voice_executor.mcp_client._initialize_mcp_session()
                    
                    # Test with a simple query to verify Cosmos DB access through MCP
                    test_result = await self.voice_executor.mcp_client.query_cosmos_data("SELECT TOP 1 * FROM c")
                    mcp_ready = bool(test_result)
                    logger.info("✅ MCP fallback system ready")
                    
                except Exception as mcp_error:
                    logger.warning(f"⚠️ MCP fallback system issue: {mcp_error}")
                
                # Determine overall readiness
                if direct_cosmos_ready:
                    return JSONResponse(content={
                        "status": "success",
                        "message": "All systems ready for chat - direct Cosmos DB primary, MCP fallback available",
                        "ready": True,
                        "direct_cosmos_ready": True,
                        "mcp_fallback_ready": mcp_ready,
                        "primary_method": "direct_cosmos",
                        "voice_agent_ready": self.voice_executor.azure_voice_agent is not None
                    })
                elif mcp_ready:
                    return JSONResponse(content={
                        "status": "success",
                        "message": "Chat ready with MCP data access (direct Cosmos not available)",
                        "ready": True,
                        "direct_cosmos_ready": False,
                        "mcp_fallback_ready": True,
                        "primary_method": "mcp_only",
                        "voice_agent_ready": self.voice_executor.azure_voice_agent is not None
                    })
                else:
                    return JSONResponse(content={
                        "status": "warning",
                        "message": "Voice agent ready, but database connections need warming up",
                        "ready": True,
                        "direct_cosmos_ready": False,
                        "mcp_fallback_ready": False,
                        "primary_method": "none",
                        "voice_agent_ready": self.voice_executor.azure_voice_agent is not None
                    })
                    
            except Exception as e:
                logger.error(f"❌ Error in startup initialization: {e}")
                return JSONResponse(content={
                    "status": "error",
                    "message": f"Initialization failed: {str(e)}",
                    "ready": False
                })
        
        # ADDED: Database readiness check endpoint
        @self.app.get("/api/database/status")
        async def check_database_status():
            """Check if database systems are accessible (direct Cosmos + MCP fallback)"""
            try:
                if not self.voice_executor:
                    return JSONResponse(content={
                        "status": "error",
                        "message": "Voice executor not available",
                        "ready": False
                    })
                
                # Check direct Cosmos DB (primary)
                direct_cosmos_status = {"ready": False, "response_time_ms": None, "error": None}
                try:
                    start_time = time.time()
                    if hasattr(self.voice_executor, 'direct_cosmos_client') and self.voice_executor.direct_cosmos_client:
                        connection_ok = await self.voice_executor.direct_cosmos_client.check_connection()
                        response_time = time.time() - start_time
                        direct_cosmos_status = {
                            "ready": connection_ok,
                            "response_time_ms": round(response_time * 1000, 2),
                            "error": None if connection_ok else "Connection test failed"
                        }
                    else:
                        direct_cosmos_status["error"] = "Direct Cosmos client not initialized"
                except Exception as e:
                    response_time = time.time() - start_time
                    direct_cosmos_status = {
                        "ready": False,
                        "response_time_ms": round(response_time * 1000, 2),
                        "error": str(e)
                    }
                
                # Check MCP fallback
                mcp_status = {"ready": False, "response_time_ms": None, "error": None, "session_id": None}
                try:
                    start_time = time.time()
                    test_result = await self.voice_executor.mcp_client.query_cosmos_data("SELECT TOP 1 * FROM c")
                    response_time = time.time() - start_time
                    mcp_status = {
                        "ready": bool(test_result),
                        "response_time_ms": round(response_time * 1000, 2),
                        "error": None if test_result else "Query returned empty result",
                        "session_id": self.voice_executor.mcp_client.session_id
                    }
                except Exception as e:
                    response_time = time.time() - start_time
                    mcp_status = {
                        "ready": False,
                        "response_time_ms": round(response_time * 1000, 2),
                        "error": str(e),
                        "session_id": self.voice_executor.mcp_client.session_id
                    }
                
                # Overall status
                overall_ready = direct_cosmos_status["ready"] or mcp_status["ready"]
                primary_method = "direct_cosmos" if direct_cosmos_status["ready"] else ("mcp_fallback" if mcp_status["ready"] else "none")
                
                return JSONResponse(content={
                    "status": "success" if overall_ready else "error",
                    "message": f"Database systems check complete - primary method: {primary_method}",
                    "ready": overall_ready,
                    "primary_method": primary_method,
                    "direct_cosmos": direct_cosmos_status,
                    "mcp_fallback": mcp_status
                })
                
            except Exception as e:
                return JSONResponse(content={
                    "status": "error",
                    "message": f"Database status check failed: {str(e)}",
                    "ready": False
                })
        
        # Cosmos DB API endpoints for voice client
        @self.app.get("/api/claims/{claim_id}")
        async def get_claim(claim_id: str):
            """Get specific claim information directly from Cosmos DB"""
            try:
                from shared.cosmos_db_client import query_claims
                
                # Normalize claim ID (add hyphen if missing)
                normalized_claim_id = claim_id.upper()
                if not '-' in normalized_claim_id and len(normalized_claim_id) >= 4:
                    normalized_claim_id = normalized_claim_id[:2] + '-' + normalized_claim_id[2:]
                
                # Query Cosmos DB directly
                claims = await query_claims(search_term=normalized_claim_id)
                
                if not claims:
                    return JSONResponse(content={"error": f"Claim {claim_id} not found"}, status_code=404)
                
                # Return the first matching claim
                claim = claims[0]
                return JSONResponse(content=claim)
                
            except Exception as e:
                logger.error(f"Error getting claim {claim_id}: {e}")
                return JSONResponse(content={"error": str(e)}, status_code=500)
        
        @self.app.get("/api/claims/search")
        async def search_claims(q: str):
            """Search claims directly from Cosmos DB"""
            try:
                from shared.cosmos_db_client import query_claims, get_all_claims
                
                if q:
                    # Search for specific term
                    claims = await query_claims(search_term=q)
                else:
                    # Get all claims if no search term
                    claims = await get_all_claims()
                
                # Return search results in expected format
                return JSONResponse(content={
                    "results": claims[:10]  # Limit to first 10 results
                })
                
            except Exception as e:
                logger.error(f"Error searching claims with query '{q}': {e}")
                return JSONResponse(content={"error": str(e)}, status_code=500)
    
    async def initialize_agent(self):
        """Initialize the voice agent executor and agent card"""
        try:
            logger.info("🚀 Starting Client Live Voice Agent...")
            logger.info("🔧 Port: 8007")
            logger.info("🎯 Mode: FastAPI Server with A2A Protocol and WebSocket Support")
            
            # Create the voice agent executor
            self.voice_executor = VoiceAgentExecutor()
            
            # Initialize the agent
            await self.voice_executor.initialize()
            
            # ADDED: Additional database readiness check to ensure Cosmos DB is ready for immediate queries
            try:
                logger.info("🔧 Performing database readiness check for immediate query capability...")
                
                direct_cosmos_ready = False
                mcp_ready = False
                
                # Test direct Cosmos DB connection first (primary)
                if hasattr(self.voice_executor, 'direct_cosmos_client') and self.voice_executor.direct_cosmos_client:
                    try:
                        test_result = await self.voice_executor.direct_cosmos_client.check_connection()
                        if test_result:
                            logger.info("✅ Direct Cosmos DB ready - primary data access confirmed")
                            direct_cosmos_ready = True
                            
                            # ADDED: Verify we can actually query data
                            try:
                                test_claims = await self.voice_executor.direct_cosmos_client.get_all_claims()
                                logger.info(f"✅ Direct Cosmos DB data access verified - {len(test_claims)} claims available")
                            except Exception as query_error:
                                logger.warning(f"⚠️ Direct Cosmos DB connection OK but query failed: {query_error}")
                        else:
                            logger.warning("⚠️ Direct Cosmos DB connection issue")
                    except Exception as e:
                        logger.warning(f"⚠️ Direct Cosmos DB test failed: {e}")
                else:
                    logger.warning("⚠️ Direct Cosmos DB client not initialized")
                
                # Test MCP fallback connection
                try:
                    test_result = await self.voice_executor.mcp_client.query_cosmos_data("test connection")
                    if test_result and "error" not in test_result.lower():
                        logger.info("✅ MCP fallback system ready")
                        mcp_ready = True
                    else:
                        logger.warning("⚠️ MCP fallback system not ready")
                except Exception as e:
                    logger.warning(f"⚠️ MCP fallback test failed: {e}")
                
                # Report overall status
                if direct_cosmos_ready and mcp_ready:
                    logger.info("✅ Database systems ready - direct Cosmos (primary) + MCP (fallback)")
                elif direct_cosmos_ready:
                    logger.info("✅ Database systems ready - direct Cosmos (primary only)")
                elif mcp_ready:
                    logger.info("✅ Database systems ready - MCP (fallback only)")
                else:
                    logger.warning("⚠️ Database systems not ready at startup - will initialize on first query")
                    
            except Exception as e:
                logger.warning(f"⚠️ Database readiness check failed: {e}")
                logger.info("📋 Database systems will initialize on first user query")
            
            # ADDED: Connect voice executor to WebSocket handler for Azure thread storage
            voice_websocket_handler.voice_executor = self.voice_executor
            logger.info("✅ Voice executor connected to WebSocket handler for Azure thread storage")
            
            # Create agent capabilities
            agent_capabilities = AgentCapabilities(
                streaming=True,
                extensions=None,
                push_notifications=None,
                state_transition_history=None
            )
            
            # Create agent card
            try:
                self.agent_card = AgentCard(
                    name="ClientLiveVoiceAgent",
                    description="Voice-enabled insurance claims assistant with real-time interaction, Azure AI Foundry integration, and WebSocket support for Voice Live API",
                    url="http://localhost:8007/",
                    version="1.0.0",
                    default_input_modes=['audio', 'text'],
                    default_output_modes=['audio', 'text'],
                    capabilities=agent_capabilities,
                    skills=[
                        AgentSkill(
                            id="voice_claims_lookup",
                            name="Voice Claims Lookup",
                            description="Voice-based insurance claims lookup and status checking with real-time interaction via WebSocket",
                            tags=['voice', 'claims', 'lookup', 'real-time', 'azure', 'websocket'],
                            examples=[
                                'Check the status of my claim',
                                'Look up claim number 12345',
                                'What is the status of my insurance claim?',
                                'Find details about my recent claim'
                            ]
                        ),
                        AgentSkill(
                            id="voice_definitions",
                            name="Voice Insurance Definitions",
                            description="Voice-based insurance term definitions and explanations with WebSocket support",
                            tags=['voice', 'definitions', 'explanations', 'insurance', 'terms', 'websocket'],
                            examples=[
                                'What is a deductible?',
                                'Explain what comprehensive coverage means',
                                'Define collision coverage',
                                'What does liability insurance cover?'
                            ]
                        ),
                        AgentSkill(
                            id="voice_document_upload",
                            name="Voice Document Upload Assistant",
                            description="Voice-guided document upload assistance for claims processing with real-time guidance",
                            tags=['voice', 'documents', 'upload', 'guidance', 'claims', 'real-time'],
                            examples=[
                                'Help me upload photos of my accident',
                                'Guide me through document submission',
                                'What documents do I need for my claim?',
                                'How do I submit my repair estimates?'
                            ]
                        )
                    ]
                )
                
                logger.info("✅ Agent card created successfully")
                
            except Exception as e:
                logger.error(f"❌ Error creating agent card: {e}")
                # Create a minimal agent card for fallback
                self.agent_card = AgentCard(
                    name="ClientLiveVoiceAgent",
                    description="Voice-enabled insurance claims assistant",
                    url="http://localhost:8007/",
                    version="1.0.0",
                    default_input_modes=['audio', 'text'],
                    default_output_modes=['audio', 'text'],
                    capabilities=agent_capabilities,
                    skills=[]
                )
            
            logger.info("✅ Voice Agent initialized successfully")
            logger.info("🎤 Ready to accept voice interactions on http://localhost:8007")
            logger.info("📝 Conversation tracking enabled - logs saved to voice_chat.json")
            logger.info("🔌 WebSocket endpoint available at ws://localhost:8007/ws/voice")
            logger.info("🌐 A2A agent card available at http://localhost:8007/.well-known/agent.json")
            
        except Exception as e:
            logger.error(f"❌ Error initializing voice agent: {e}")
            raise

def create_app():
    """Create and configure the FastAPI app"""
    server = VoiceFastAPIServer()
    return server

async def startup_event():
    """Startup event handler"""
    # Initialize the agent when the app starts
    app_instance = create_app()
    await app_instance.initialize_agent()
    return app_instance.app

def start_server():
    """Start the voice agent server"""
    try:
        # Create the app
        server = VoiceFastAPIServer()
        
        # Run initialization
        async def init_and_run():
            await server.initialize_agent()
            return server.app
        
        app = asyncio.run(init_and_run())
        
        # Start the server
        uvicorn.run(app, host="0.0.0.0", port=8007, log_level="info")
        
    except KeyboardInterrupt:
        logger.info("🛑 Voice Agent stopped by user")
    except Exception as e:
        logger.error(f"❌ Error starting Voice Agent: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    start_server()