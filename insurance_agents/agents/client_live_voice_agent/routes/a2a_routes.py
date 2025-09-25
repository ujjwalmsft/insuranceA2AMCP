"""
A2A protocol endpoints
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from config import AGENT_ID, get_logger
from utils import create_error_response

logger = get_logger(__name__)
router = APIRouter()

# This will be injected by the main server
agent_card = None

def set_agent_card(card):
    """Set the agent card instance"""
    global agent_card
    agent_card = card

@router.get("/.well-known/agent.json")
async def get_agent_card():
    """A2A Agent Card endpoint"""
    if not agent_card:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        # Convert AgentCard to dict dynamically
        agent_dict = agent_card.model_dump()
        
        # Convert field names from snake_case to camelCase for A2A compatibility
        formatted_dict = {
            "name": agent_dict.get("name"),
            "description": agent_dict.get("description"),
            "url": agent_dict.get("url"),
            "version": agent_dict.get("version"),
            "id": AGENT_ID,  # Add id field for A2A compatibility
            "defaultInputModes": agent_dict.get("default_input_modes", []),
            "defaultOutputModes": agent_dict.get("default_output_modes", []),
            "instructions": "Provides voice-based insurance claims assistance with Azure AI Foundry integration and real-time WebSocket communication",
            "capabilities": agent_dict.get("capabilities", {}),
            "skills": agent_dict.get("skills", [])
        }
        
        # Convert capabilities if it's an object
        if hasattr(agent_card.capabilities, 'model_dump'):
            formatted_dict["capabilities"] = agent_card.capabilities.model_dump()
        
        # Add custom voice capabilities for testing
        if "capabilities" not in formatted_dict:
            formatted_dict["capabilities"] = {}
        
        formatted_dict["capabilities"]["audio"] = True
        formatted_dict["capabilities"]["voice"] = True
        formatted_dict["capabilities"]["real_time"] = True
        
        # Convert skills if they're objects
        if agent_card.skills:
            formatted_dict["skills"] = [
                skill.model_dump() if hasattr(skill, 'model_dump') else skill
                for skill in agent_card.skills
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
            "id": AGENT_ID,
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