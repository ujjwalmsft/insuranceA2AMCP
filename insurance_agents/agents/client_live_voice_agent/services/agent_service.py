"""
Agent service for handling voice agent initialization and management
"""
import time
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from config import AGENT_NAME, AGENT_URL, AGENT_INPUT_MODES, AGENT_OUTPUT_MODES, get_logger

# Import voice components (handle both relative and absolute imports)
try:
    from ..voice_agent_executor import VoiceAgentExecutor
    from ..voice_websocket_handler import voice_websocket_handler
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from voice_agent_executor import VoiceAgentExecutor
    from voice_websocket_handler import voice_websocket_handler

logger = get_logger(__name__)

class AgentService:
    """Service for managing voice agent lifecycle"""
    
    def __init__(self):
        self.voice_executor = None
        self.agent_card = None
    
    async def initialize(self) -> AgentCard:
        """Initialize the voice agent executor and create agent card"""
        try:
            # Create the voice agent executor
            self.voice_executor = VoiceAgentExecutor()
            
            # Initialize the agent
            await self.voice_executor.initialize()
            
            # Perform database readiness check
            await self._check_database_readiness()
            
            # Connect voice executor to WebSocket handler
            voice_websocket_handler.voice_executor = self.voice_executor
            logger.info("✅ Voice executor connected to WebSocket handler for Azure thread storage")
            
            # Create and return agent card
            self.agent_card = self._create_agent_card()
            logger.info("✅ Agent card created successfully")
            
            return self.agent_card
            
        except Exception as e:
            logger.error(f"❌ Error initializing voice agent: {e}")
            raise
    
    async def _check_database_readiness(self):
        """Check database system readiness"""
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
                        
                        # Verify we can actually query data
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
    
    def _create_agent_card(self) -> AgentCard:
        """Create agent card with capabilities and skills"""
        try:
            # Create agent capabilities
            agent_capabilities = AgentCapabilities(
                streaming=True,
                extensions=None,
                push_notifications=None,
                state_transition_history=None
            )
            
            # Create agent card
            return AgentCard(
                name=AGENT_NAME,
                description="Voice-enabled insurance claims assistant with real-time interaction, Azure AI Foundry integration, and WebSocket support for Voice Live API",
                url=AGENT_URL,
                version="1.0.0",
                default_input_modes=AGENT_INPUT_MODES,
                default_output_modes=AGENT_OUTPUT_MODES,
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
            
        except Exception as e:
            logger.error(f"❌ Error creating agent card: {e}")
            # Create a minimal agent card for fallback
            return AgentCard(
                name=AGENT_NAME,
                description="Voice-enabled insurance claims assistant",
                url=AGENT_URL,
                version="1.0.0",
                default_input_modes=AGENT_INPUT_MODES,
                default_output_modes=AGENT_OUTPUT_MODES,
                capabilities=AgentCapabilities(streaming=True),
                skills=[]
            )