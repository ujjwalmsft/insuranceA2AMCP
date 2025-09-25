"""
Unified Insurance Management Dashboard

A comprehensive web dashboard that provides both claims processing and agent registry
management on a single service. Features seamless navigation between employee claims
dashboard and admin agent registry dashboard.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Optional
from pathlib import Path

# Add the parent directory to the path so we can import shared modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import aiohttp
import uvicorn
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Import shared modules
try:
    from shared.dynamic_workflow_logger import workflow_logger, WorkflowStepType, WorkflowStepStatus
    print("✅ Successfully imported dynamic workflow_logger with enums")
except ImportError as e:
    print(f"⚠️ Failed to import dynamic workflow_logger: {e}")
    # Create a mock workflow logger if import fails
    class MockWorkflowLogger:
        def get_workflow_steps(self, claim_id):
            print(f"⚠️ MockWorkflowLogger: get_workflow_steps called for {claim_id}")
            return []
        def get_all_recent_steps(self, limit):
            print(f"⚠️ MockWorkflowLogger: get_all_recent_steps called with limit {limit}")
            return []
    workflow_logger = MockWorkflowLogger()
    # Mock enums for fallback
    class WorkflowStepType:
        DISCOVERY = "discovery"
    class WorkflowStepStatus:
        COMPLETED = "completed"

# Import our orchestrator
try:
    from insurance_agents.agents.claims_orchestrator.intelligent_orchestrator_executor import IntelligentClaimsOrchestrator
    print("✅ Successfully imported intelligent orchestrator")
    ORCHESTRATOR_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Intelligent orchestrator not available: {e}")
    ORCHESTRATOR_AVAILABLE = False

# Active Processing State Management
active_processing_sessions = {}  # Track which claims are being actively processed
current_viewing_claim = None     # Track which claim's steps should be shown
current_processing_claims = set()  # Track currently processing claims for real-time updates
processing_steps_cache = {}  # Short-term memory cache for real-time steps

def start_claim_processing_session(claim_id: str):
    """Mark a claim as actively being processed"""
    global active_processing_sessions, current_processing_claims, processing_steps_cache
    active_processing_sessions[claim_id] = {
        "start_time": datetime.now().isoformat(),
        "status": "processing",
        "session_id": str(uuid.uuid4())
    }
    current_processing_claims.add(claim_id)
    # Clear any old cached steps for this claim to ensure fresh real-time data
    processing_steps_cache[claim_id] = []
    terminal_logger.log("INFO", "SESSION", f"✅ Started processing session for claim {claim_id}")
    terminal_logger.log("DEBUG", "SESSION", f"   Active claims: {list(current_processing_claims)}")
    terminal_logger.log("DEBUG", "SESSION", f"   Total sessions: {len(active_processing_sessions)}")

def end_claim_processing_session(claim_id: str):
    """Mark a claim processing as complete"""
    global active_processing_sessions, current_processing_claims
    if claim_id in active_processing_sessions:
        active_processing_sessions[claim_id]["status"] = "completed"
        active_processing_sessions[claim_id]["end_time"] = datetime.now().isoformat()
    current_processing_claims.discard(claim_id)
    # Keep steps in cache briefly for completed claims
    terminal_logger.log("INFO", "SESSION", f"🏁 Ended processing session for claim {claim_id}")
    terminal_logger.log("DEBUG", "SESSION", f"   Remaining active claims: {list(current_processing_claims)}")

def is_claim_actively_processing(claim_id: str) -> bool:
    """Check if a claim is currently being processed"""
    result = claim_id in current_processing_claims
    terminal_logger.log("DEBUG", "SESSION", f"   Is {claim_id} active? {result}")
    return result

def get_real_time_processing_steps(claim_id: str = None):
    """Get real-time processing steps only for actively processing claims"""
    terminal_logger.log("DEBUG", "STEPS", f"🔍 Getting real-time steps for claim: {claim_id or 'all'}")
    terminal_logger.log("DEBUG", "STEPS", f"   Current processing claims: {list(current_processing_claims)}")
    
    # Only return steps if there are actively processing claims
    if not current_processing_claims:
        terminal_logger.log("DEBUG", "STEPS", "   No active processing claims - returning empty")
        return []
    
    # Force refresh from file to get latest data
    workflow_logger._load_from_file()
    
    if claim_id and is_claim_actively_processing(claim_id):
        # Get LIVE steps for specific actively processing claim
        live_steps = workflow_logger.get_workflow_steps(claim_id)
        processing_steps_cache[claim_id] = live_steps
        terminal_logger.log("DEBUG", "STEPS", f"   Retrieved {len(live_steps)} steps for active claim {claim_id}")
        return live_steps
    elif not claim_id:
        # Get steps for any actively processing claims
        all_active_steps = []
        
        for active_claim_id in current_processing_claims:
            claim_steps = workflow_logger.get_workflow_steps(active_claim_id)
            # Filter to only this specific claim's steps
            filtered_steps = [step for step in claim_steps if isinstance(step, dict) and step.get('claim_id') == active_claim_id]
            processing_steps_cache[active_claim_id] = filtered_steps
            all_active_steps.extend(filtered_steps)
            terminal_logger.log("DEBUG", "STEPS", f"   Retrieved {len(filtered_steps)} steps for active claim {active_claim_id}")
        
        terminal_logger.log("DEBUG", "STEPS", f"   Total active steps across all claims: {len(all_active_steps)}")
        return all_active_steps
    
    # No active processing for this claim
    terminal_logger.log("DEBUG", "STEPS", f"   Claim {claim_id} is not actively being processed")
    return []

def get_active_processing_steps(claim_id: str = None):
    """Get workflow steps only for actively processing claims (enhanced with real-time)"""
    return get_real_time_processing_steps(claim_id)

# Load environment variables
load_dotenv()

# Configure logging with terminal colors
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TerminalLogger:
    """Terminal logging for the dashboard"""
    
    COLORS = {
        'reset': '\033[0m', 'bold': '\033[1m', 'red': '\033[91m',
        'green': '\033[92m', 'yellow': '\033[93m', 'blue': '\033[94m',
        'magenta': '\033[95m', 'cyan': '\033[96m'
    }
    
    @classmethod
    def log(cls, level: str, component: str, message: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        emoji_map = {
            'INFO': '📋', 'SUCCESS': '✅', 'WARNING': '⚠️', 'ERROR': '❌',
            'DASHBOARD': '🖥️', 'CLAIM': '🏥', 'AGENT': '🤖'
        }
        color_map = {
            'INFO': cls.COLORS['blue'], 'SUCCESS': cls.COLORS['green'],
            'WARNING': cls.COLORS['yellow'], 'ERROR': cls.COLORS['red'],
            'DASHBOARD': cls.COLORS['cyan'], 'CLAIM': cls.COLORS['magenta'],
            'AGENT': cls.COLORS['green']
        }
        
        emoji = emoji_map.get(level, '📋')
        color = color_map.get(level, cls.COLORS['blue'])
        console_message = f"{color}[{timestamp}] {emoji} {component.upper()}: {message}{cls.COLORS['reset']}"
        print(console_message)
        
        # Also add to processing logs for the Recent Activity section
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "component": component,
            "message": message,
            "emoji": emoji
        }
        processing_logs.append(log_entry)
        
        # Keep only last 100 logs to prevent memory issues
        if len(processing_logs) > 100:
            processing_logs.pop(0)

# Data Models
class ClaimStatus(BaseModel):
    """Claim processing status"""
    claimId: str
    status: str  # submitted, processing, approved, pended, denied
    category: str  # Outpatient, Inpatient
    amountBilled: float
    submitDate: str
    lastUpdate: str
    assignedEmployee: Optional[str] = None
    # Additional fields to fix "undefined" issues in UI
    patientName: Optional[str] = None
    provider: Optional[str] = None
    memberId: Optional[str] = None
    region: Optional[str] = None
    
    # Add aliases for HTML template compatibility
    amount: Optional[float] = None  # Will be set to amountBilled
    submitted: Optional[str] = None  # Will be set to submitDate
    
    def __init__(self, **data):
        super().__init__(**data)
        # Set aliases automatically
        self.amount = self.amountBilled
        self.submitted = self.submitDate

class AgentInfo(BaseModel):
    """Insurance agent information"""
    agentId: str
    name: str
    type: str  # orchestrator, specialist
    status: str  # online, offline, busy, error
    capabilities: List[str]
    lastActivity: str
    currentClaims: List[str]

class ProcessingRequest(BaseModel):
    """Claim processing request"""
    claimId: str
    expectedOutput: str
    priority: str = "normal"
    employeeId: str

class ChatMessage(BaseModel):
    """Chat message model"""
    message: str
    sessionId: str
    timestamp: str

class ChatResponse(BaseModel):
    """Enhanced chat response model with workflow support"""
    response: str  # Changed from message to response for compatibility
    sessionId: str
    timestamp: str
    status: Optional[str] = "completed"
    claim_id: Optional[str] = None
    requires_confirmation: Optional[bool] = False
    final_decision: Optional[str] = None

# Initialize FastAPI app
app = FastAPI(
    title="Unified Insurance Management Dashboard",
    description="Comprehensive dashboard for claims processing and agent registry management",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state (in production, this would be in a database)
active_claims: Dict[str, ClaimStatus] = {}
registered_agents: Dict[str, AgentInfo] = {}
agent_cards: Dict[str, Dict] = {}  # Store agent cards for detailed info
processing_logs: List[Dict] = []
chat_sessions: Dict[str, List[Dict]] = {}  # Store chat history by session ID

# Custom agents storage
CUSTOM_AGENTS_FILE = Path(__file__).parent / "custom_agents.json"
custom_agents: Dict[str, Dict] = {}  # Store user-added custom agents

terminal_logger = TerminalLogger()

# WebSocket connection management for real-time notifications
websocket_connections: List[WebSocket] = []

class NotificationManager:
    """Manages real-time notifications to connected clients"""
    
    @staticmethod
    async def send_notification(notification_type: str, data: Dict[str, Any]):
        """Send notification to all connected clients"""
        if not websocket_connections:
            return
        
        notification = {
            "type": notification_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        
        terminal_logger.log("NOTIFICATION", "SEND", f"📢 Sending {notification_type} notification to {len(websocket_connections)} clients")
        
        # Send to all connected clients
        disconnected = []
        for websocket in websocket_connections:
            try:
                await websocket.send_json(notification)
            except Exception as e:
                terminal_logger.log("WARNING", "WEBSOCKET", f"Failed to send notification: {e}")
                disconnected.append(websocket)
        
        # Remove disconnected clients
        for ws in disconnected:
            websocket_connections.remove(ws)
    
    @staticmethod
    async def send_email_notification(claim_id: str, email_status: str, details: Dict[str, Any]):
        """Send email-specific notification"""
        await NotificationManager.send_notification("email_notification", {
            "claim_id": claim_id,
            "email_status": email_status,
            "details": details,
            "message": f"Email notification {email_status} for claim {claim_id}"
        })

notification_manager = NotificationManager()

@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """WebSocket endpoint for real-time notifications"""
    await websocket.accept()
    websocket_connections.append(websocket)
    
    terminal_logger.log("WEBSOCKET", "CONNECT", f"📡 Client connected. Total connections: {len(websocket_connections)}")
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connection_established",
            "data": {"message": "Connected to notification system"},
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep connection alive
        while True:
            # Wait for any messages from client (heartbeat, etc.)
            try:
                data = await websocket.receive_json()
                # Handle client messages if needed
                if data.get("type") == "heartbeat":
                    await websocket.send_json({
                        "type": "heartbeat_response",
                        "timestamp": datetime.now().isoformat()
                    })
            except WebSocketDisconnect:
                break
            except Exception as e:
                terminal_logger.log("WARNING", "WEBSOCKET", f"WebSocket error: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        websocket_connections.remove(websocket)
        terminal_logger.log("WEBSOCKET", "DISCONNECT", f"📡 Client disconnected. Total connections: {len(websocket_connections)}")

@app.on_event("startup")
async def startup_event():
    """Initialize dashboard on startup"""
    terminal_logger.log("DASHBOARD", "STARTUP", "Insurance Claims Processing Dashboard starting...")
    
    # Load custom agents from file
    load_custom_agents()
    
    # Initialize orchestrator if available
    if ORCHESTRATOR_AVAILABLE:
        terminal_logger.log("DASHBOARD", "STARTUP", "Initializing intelligent orchestrator...")
        # Initialize the orchestrator (no need to store globally, we'll create instances as needed)
        terminal_logger.log("SUCCESS", "DASHBOARD", "Orchestrator available for use")
    
    # Initialize real agents with health checking
    await initialize_demo_agents()
    
    # Start background task to refresh agent status every 30 seconds
    asyncio.create_task(refresh_agent_status_periodically())
    
    # Load sample claims
    await load_sample_claims()
    
    terminal_logger.log("SUCCESS", "DASHBOARD", "Dashboard initialized successfully on http://localhost:3000")

def load_custom_agents():
    """Load custom agents from the JSON file"""
    global custom_agents
    try:
        if CUSTOM_AGENTS_FILE.exists():
            with open(CUSTOM_AGENTS_FILE, 'r') as f:
                custom_agents = json.load(f)
            terminal_logger.log("SUCCESS", "STORAGE", f"Loaded {len(custom_agents)} custom agents")
        else:
            custom_agents = {}
            terminal_logger.log("INFO", "STORAGE", "No custom agents file found, starting with empty registry")
    except Exception as e:
        terminal_logger.log("ERROR", "STORAGE", f"Failed to load custom agents: {e}")
        custom_agents = {}

def save_custom_agents():
    """Save custom agents to the JSON file"""
    try:
        with open(CUSTOM_AGENTS_FILE, 'w') as f:
            json.dump(custom_agents, f, indent=2)
        terminal_logger.log("SUCCESS", "STORAGE", f"Saved {len(custom_agents)} custom agents")
    except Exception as e:
        terminal_logger.log("ERROR", "STORAGE", f"Failed to save custom agents: {e}")

async def fetch_agent_card_from_url(agent_url: str) -> tuple[bool, Dict, str]:
    """
    Fetch agent card from URL and validate it
    Returns: (success, agent_card_data, error_message)
    Note: This function now always returns success=True, but agent_card might be empty if agent is offline
    """
    try:
        # Normalize URL (ensure it doesn't end with /)
        agent_url = agent_url.rstrip('/')
        
        # Try to fetch agent card from .well-known/agent.json
        agent_card_url = f"{agent_url}/.well-known/agent.json"
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(agent_card_url) as response:
                if response.status == 200:
                    try:
                        agent_card = await response.json()
                        
                        # Add the URL to the agent card
                        agent_card['url'] = agent_url
                        
                        return True, agent_card, ""
                        
                    except json.JSONDecodeError as e:
                        # Return empty agent card with error info
                        return True, {"url": agent_url, "offline_reason": f"Invalid JSON: {e}"}, f"Invalid JSON in agent card: {e}"
                else:
                    # Return empty agent card with status info
                    return True, {"url": agent_url, "offline_reason": f"HTTP {response.status}"}, f"Agent offline: HTTP {response.status}"
                    
    except aiohttp.ClientError as e:
        # Return empty agent card with network error info
        return True, {"url": agent_url, "offline_reason": f"Network error: {e}"}, f"Network error: {e}"
    except Exception as e:
        # Return empty agent card with general error info
        return True, {"url": agent_url, "offline_reason": f"Error: {e}"}, f"Error: {e}"

async def register_custom_agents():
    """Register all custom agents from storage into the main registry"""
    for agent_id, custom_agent in custom_agents.items():
        agent_card = custom_agent.get("agent_card", {})
        agent_name = agent_card.get("name", agent_id)
        agent_url = custom_agent.get("url", "")
        
        # Register in main agents registry
        registered_agents[agent_id] = AgentInfo(
            agentId=agent_id,
            name=agent_name,
            type="custom",
            status="unknown",  # Will be checked in background
            capabilities=[], # Could extract from agent card skills if available
            lastActivity=datetime.now().isoformat(),
            currentClaims=[]
        )
        
        # Store agent card for detailed view
        agent_cards[agent_id] = agent_card
        
        # Check status
        asyncio.create_task(check_and_update_custom_agent_status(agent_id))
        
        terminal_logger.log("CUSTOM_AGENT", "REGISTRATION", 
            f"Registered custom agent: {agent_name} ({agent_url})")

async def initialize_demo_agents():
    """Initialize and monitor real insurance agents"""
    # Real agent endpoints (same as your actual agents)
    real_agents = [
        {
            "agentId": "claims_orchestrator",
            "name": "Claims Orchestrator", 
            "url": "http://localhost:8001",
            "type": "orchestrator",
            "capabilities": ["workflow_orchestration", "agent_routing", "decision_aggregation"]
        },
        {
            "agentId": "intake_clarifier",
            "name": "Intake Clarifier",
            "url": "http://localhost:8002", 
            "type": "specialist",
            "capabilities": ["intake_validation", "completeness_check", "gap_analysis"]
        },
        {
            "agentId": "document_intelligence", 
            "name": "Document Intelligence",
            "url": "http://localhost:8003",
            "type": "specialist",
            "capabilities": ["document_processing", "text_extraction", "evidence_tagging"]
        },
        {
            "agentId": "coverage_rules_engine",
            "name": "Coverage Rules Engine", 
            "url": "http://localhost:8004",
            "type": "specialist",
            "capabilities": ["coverage_evaluation", "policy_analysis", "decision_engine"]
        }
    ]
    
    # Check real agent status and register them
    for agent_config in real_agents:
        status = await check_real_agent_health(agent_config["url"], agent_config["agentId"])
        
        registered_agents[agent_config["agentId"]] = AgentInfo(
            agentId=agent_config["agentId"],
            name=agent_config["name"],
            type=agent_config["type"],
            status=status,
            capabilities=agent_config["capabilities"],
            lastActivity=datetime.now().isoformat(),
            currentClaims=[]
        )
        
        terminal_logger.log("AGENT", "REGISTRATION", 
            f"Agent {agent_config['name']} registered with status: {status}")
    
    # Also register custom agents from storage
    await register_custom_agents()

async def check_real_agent_health(agent_url: str, agent_id: str = None) -> str:
    """Check if a real agent is online and fetch its agent card"""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
            # Try multiple endpoints to determine if agent is alive
            endpoints_to_try = [
                f"{agent_url}/.well-known/agent.json",  # A2A standard
                f"{agent_url}/health",                   # Health check
                f"{agent_url}/",                         # Root endpoint
                f"{agent_url}/docs"                      # FastAPI docs
            ]
            
            for endpoint in endpoints_to_try:
                try:
                    async with session.get(endpoint) as response:
                        if response.status == 200:
                            # If it's the agent card endpoint, store the card
                            if endpoint.endswith("agent.json") and agent_id:
                                try:
                                    agent_card = await response.json()
                                    agent_cards[agent_id] = agent_card
                                    terminal_logger.log("SUCCESS", "AGENT_CARD", 
                                        f"Fetched agent card for {agent_card.get('name', agent_id)}")
                                except:
                                    pass  # If JSON parsing fails, continue
                            return "online"
                except:
                    continue  # Try next endpoint
                    
            return "offline"
            
    except Exception as e:
        terminal_logger.log("WARNING", "AGENT_CHECK", f"Health check failed for {agent_url}: {e}")
        return "offline"

async def refresh_agent_status_periodically():
    """Periodically refresh agent status every 7 seconds"""
    while True:
        try:
            await asyncio.sleep(7)  # Wait 7 seconds for faster updates
            terminal_logger.log("DASHBOARD", "REFRESH", "Refreshing agent status...")
            
            # Update status for all registered agents
            for agent_id, agent_info in registered_agents.items():
                # For built-in agents, construct URL from agent_id
                port_map = {
                    "claims_orchestrator": 8001,
                    "intake_clarifier": 8002, 
                    "document_intelligence": 8003,
                    "coverage_rules_engine": 8004
                }
                
                if agent_id in port_map:
                    # Built-in agent
                    agent_url = f"http://localhost:{port_map[agent_id]}"
                    new_status = await check_real_agent_health(agent_url, agent_id)
                    
                    if agent_info.status != new_status:
                        terminal_logger.log("AGENT", "STATUS_CHANGE", 
                            f"Agent {agent_info.name}: {agent_info.status} -> {new_status}")
                        agent_info.status = new_status
                        agent_info.lastActivity = datetime.now().isoformat()
                    else:
                        # Log the status check even if no change
                        terminal_logger.log("DASHBOARD", "STATUS_CHECK", 
                            f"Agent {agent_info.name}: {new_status}")
                
                elif agent_id in custom_agents:
                    # Custom agent
                    agent_url = custom_agents[agent_id]["url"]
                    new_status = await check_real_agent_health(agent_url, agent_id)
                    
                    if agent_info.status != new_status:
                        terminal_logger.log("AGENT", "STATUS_CHANGE", 
                            f"Custom Agent {agent_info.name}: {agent_info.status} -> {new_status}")
                        agent_info.status = new_status
                        agent_info.lastActivity = datetime.now().isoformat()
                    else:
                        # Log the status check even if no change
                        terminal_logger.log("DASHBOARD", "STATUS_CHECK", 
                            f"Custom Agent {agent_info.name}: {new_status}")
                        
        except Exception as e:
            terminal_logger.log("ERROR", "REFRESH", f"Error refreshing agent status: {e}")
            await asyncio.sleep(10)  # Wait 10 seconds on error

async def load_sample_claims():
    """Load REAL claims directly from Cosmos DB - claim_details container"""
    try:
        terminal_logger.log("COSMOS", "LOADING", "Loading claims data directly from Cosmos DB claim_details container...")
        
        # Import Cosmos DB client
        from azure.cosmos import CosmosClient
        
        # Get Cosmos DB connection details from environment
        cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
        cosmos_key = os.getenv("COSMOS_KEY") 
        database_name = os.getenv("COSMOS_DATABASE", "insurance")
        container_name = "claim_details"  # Updated to correct container name
        
        if not cosmos_endpoint or not cosmos_key:
            terminal_logger.log("ERROR", "COSMOS", "Missing COSMOS_ENDPOINT or COSMOS_KEY environment variables")
            raise ValueError("Cosmos DB credentials not configured")
        
        # Create Cosmos client and query claims directly
        client = CosmosClient(cosmos_endpoint, cosmos_key)
        database = client.get_database_client(database_name)
        container = database.get_container_client(container_name)
        
        # Query all claims from claim_details container
        query = "SELECT * FROM c"
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        
        terminal_logger.log("COSMOS", "SUCCESS", f"Successfully retrieved {len(items)} claims from claim_details container")
        
        # Clear existing claims
        active_claims.clear()
        
        # Process each claim document from Cosmos DB
        for item in items:
            # Map Cosmos DB fields to ClaimStatus model
            # Use actual status from Cosmos DB document
            cosmos_status = item.get("status", "submitted")
            
            claim = ClaimStatus(
                claimId=item.get("claimId") or item.get("id", "Unknown"),
                status=cosmos_status,  # Use actual status from Cosmos DB
                category=item.get("category", "Unknown"),
                amountBilled=float(item.get("billAmount", 0)),  # Map billAmount -> amountBilled
                submitDate=item.get("billDate", ""),  # Map billDate -> submitDate
                lastUpdate=item.get("lastUpdatedAt", datetime.now().isoformat()),  # Map lastUpdatedAt -> lastUpdate
                assignedEmployee=item.get("assignedEmployeeName"),  # Map assignedEmployeeName -> assignedEmployee
                patientName=item.get("patientName", "Unknown Patient"),
                provider=determine_provider_from_claim(item),  # Derive provider from claim data
                memberId=item.get("memberId", "Unknown"),
                region=item.get("region", "US")
            )
            
            active_claims[claim.claimId] = claim
            terminal_logger.log("COSMOS", "LOAD", f"Loaded claim: {claim.claimId} - {claim.patientName} - ${claim.amountBilled} ({claim.category})")
        
        terminal_logger.log("SUCCESS", "COSMOS", f"Loaded {len(items)} real claims from Cosmos DB claim_details container")
        return
    
    except Exception as e:
        terminal_logger.log("ERROR", "COSMOS", f"Failed to load claims from Cosmos DB: {str(e)}")
        terminal_logger.log("ERROR", "COSMOS", "Make sure:")
        terminal_logger.log("ERROR", "COSMOS", "1. COSMOS_ENDPOINT and COSMOS_KEY environment variables are set")
        terminal_logger.log("ERROR", "COSMOS", "2. Cosmos DB 'insurance' database exists")
        terminal_logger.log("ERROR", "COSMOS", "3. 'claim_details' container exists with data")
        terminal_logger.log("ERROR", "COSMOS", "4. Azure Cosmos DB Python SDK is installed: pip install azure-cosmos")
    # No fallback data - we only use real Cosmos DB data
    terminal_logger.log("ERROR", "COSMOS", "No fallback data available. Please fix Cosmos DB connection.")

    # If we get here, Cosmos DB setup is needed - no more fallback sample data!
    terminal_logger.log("SETUP", "REQUIRED", "🔧 Cosmos DB setup required!")
    terminal_logger.log("SETUP", "REQUIRED", "Run: python setup_cosmos_db.py")
    terminal_logger.log("SETUP", "REQUIRED", "Then start MCP server and restart dashboard")


def determine_provider_from_claim(cosmos_doc):
    """Determine provider from Cosmos document based on category and service type"""
    category = cosmos_doc.get("category", "").lower()
    service_type = cosmos_doc.get("serviceType", "")
    employee_id = cosmos_doc.get("assignedEmployeeID", "")
    
    # Create provider codes based on claim type and employee assignment
    if "inpatient" in category:
        # Hospital provider for inpatient claims
        suffix = employee_id[-4:] if employee_id else "UNKNOWN"
        return f"HSP-{suffix}"
    elif "outpatient" in category:
        # Clinic provider for outpatient claims  
        suffix = employee_id[-4:] if employee_id else "UNKNOWN"
        return f"CLN-{suffix}"
    else:
        return "PROVIDER-UNKNOWN"

# API Endpoints

# API Endpoints

@app.get("/", response_class=HTMLResponse)
async def serve_default_dashboard():
    """Serve the default claims dashboard (employee view)"""
    html_file = Path(__file__).parent / "static" / "claims_dashboard.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding='utf-8'), status_code=200)
    else:
        return HTMLResponse(content="<h1>Claims Dashboard - HTML file not found</h1>", status_code=404)

@app.get("/claims", response_class=HTMLResponse)
async def serve_claims_dashboard():
    """Serve the claims processing dashboard (employee view)"""
    html_file = Path(__file__).parent / "static" / "claims_dashboard.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding='utf-8'), status_code=200)
    else:
        return HTMLResponse(content="<h1>Claims Dashboard - HTML file not found</h1>", status_code=404)

@app.get("/agents", response_class=HTMLResponse)
async def serve_agent_registry():
    """Serve the agent registry dashboard (admin view)"""
    html_file = Path(__file__).parent / "static" / "agent_registry.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding='utf-8'), status_code=200)
    else:
        return HTMLResponse(content="<h1>Agent Registry - HTML file not found</h1>", status_code=404)

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/claims")
async def get_claims():
    """Get all active claims with frontend-compatible field names"""
    claims_for_frontend = []
    
    for claim in active_claims.values():
        # Map backend ClaimStatus fields to frontend expected field names
        frontend_claim = {
            "claimId": claim.claimId,
            "status": claim.status,  # Already mapped (submitted -> pending) during loading
            "category": claim.category,
            "amount": claim.amountBilled,  # Map amountBilled -> amount
            "submitted": claim.submitDate,  # Map submitDate -> submitted  
            "lastUpdate": claim.lastUpdate,
            "assignedEmployee": claim.assignedEmployee,
            "patientName": claim.patientName,
            "provider": claim.provider,
            "memberId": claim.memberId,
            "region": claim.region
        }
        claims_for_frontend.append(frontend_claim)
    
    terminal_logger.log("INFO", "API", f"Retrieved {len(active_claims)} claims")
    return {"claims": claims_for_frontend}

@app.get("/api/claims/{claim_id}")
async def get_claim(claim_id: str):
    """Get specific claim details"""
    if claim_id not in active_claims:
        terminal_logger.log("WARNING", "API", f"Claim not found: {claim_id}")
        raise HTTPException(status_code=404, detail="Claim not found")
    
    terminal_logger.log("INFO", "API", f"Retrieved claim details: {claim_id}")
    return {"claim": active_claims[claim_id]}

@app.post("/api/claims/refresh")
async def refresh_claims():
    """Manual refresh endpoint to reload claims from Cosmos DB"""
    try:
        terminal_logger.log("INFO", "API", "Manual refresh triggered - reloading claims from Cosmos DB")
        await load_sample_claims()  # Reload from Cosmos DB
        return {
            "success": True, 
            "message": f"Successfully refreshed {len(active_claims)} claims from Cosmos DB",
            "count": len(active_claims)
        }
    except Exception as e:
        terminal_logger.log("ERROR", "API", f"Failed to refresh claims: {str(e)}")
        return {
            "success": False, 
            "message": f"Failed to refresh claims: {str(e)}"
        }

@app.get("/api/agents")
async def get_agents():
    """Get all registered agents (built-in + custom)"""
    # The registered_agents dict already contains both built-in and custom agents
    agents_list = list(registered_agents.values())
    terminal_logger.log("INFO", "API", f"Retrieved {len(agents_list)} agents ({len(custom_agents)} custom)")
    return {"agents": agents_list}

@app.get("/api/agent-card/{agent_id}")
async def get_agent_card(agent_id: str):
    """Get detailed agent card information"""
    if agent_id in agent_cards:
        terminal_logger.log("INFO", "API", f"Retrieved agent card for {agent_id}")
        return {"success": True, "agentCard": agent_cards[agent_id]}
    else:
        terminal_logger.log("WARNING", "API", f"Agent card not found for {agent_id}")
        return {"success": False, "error": "Agent card not found"}

@app.post("/api/agents")
async def add_custom_agent(request: Request):
    """Add a custom agent by URL with optional custom name"""
    try:
        data = await request.json()
        agent_url = data.get("url", "").strip()
        custom_name = data.get("name", "").strip()
        
        if not agent_url:
            return {"success": False, "error": "Agent URL is required"}
        
        if not custom_name:
            return {"success": False, "error": "Agent name is required"}
        
        # Validate URL format
        if not agent_url.startswith(("http://", "https://")):
            return {"success": False, "error": "URL must start with http:// or https://"}
        
        # Normalize URL
        agent_url = agent_url.rstrip('/')
        
        # Check if agent already exists (by URL)
        for existing_id, existing_agent in custom_agents.items():
            if existing_agent.get("url") == agent_url:
                return {"success": False, "error": f"Agent already exists with ID: {existing_id}"}
        
        # Check if it conflicts with built-in agents
        for existing_id, existing_agent in registered_agents.items():
            # For built-in agents, we need to construct their URL
            if existing_id in ["claims_orchestrator", "intake_clarifier", "document_intelligence", "coverage_rules_engine"]:
                port_map = {
                    "claims_orchestrator": 8001,
                    "intake_clarifier": 8002,
                    "document_intelligence": 8003,
                    "coverage_rules_engine": 8004
                }
                built_in_url = f"http://localhost:{port_map[existing_id]}"
                if agent_url == built_in_url:
                    return {"success": False, "error": f"This URL belongs to the built-in agent: {existing_agent.name}"}
        
        # Try to fetch agent card (but don't fail if it's not available)
        success, agent_card, error_msg = await fetch_agent_card_from_url(agent_url)
        
        # Use custom name, or fall back to agent card name, or use a default
        agent_name = custom_name
        if not agent_name and agent_card.get("name"):
            agent_name = agent_card.get("name")
        if not agent_name:
            agent_name = f"Custom Agent ({agent_url.split('//')[-1]})"
        
        # Generate a unique agent ID based on custom name
        agent_id = agent_name.lower().replace(" ", "_").replace("-", "_")
        # Remove any special characters
        import re
        agent_id = re.sub(r'[^a-z0-9_]', '', agent_id)
        
        # Ensure unique ID
        counter = 1
        original_id = agent_id
        while agent_id in custom_agents or agent_id in registered_agents:
            agent_id = f"{original_id}_{counter}"
            counter += 1
        
        # Create a basic agent card if none exists
        if not agent_card or not agent_card.get("name"):
            agent_card = {
                "name": agent_name,
                "description": f"Custom agent at {agent_url}",
                "version": "unknown",
                "url": agent_url,
                "custom_agent": True,
                "offline_reason": agent_card.get("offline_reason", "Agent card not available")
            }
        else:
            agent_card["custom_agent"] = True
        
        # Store the custom agent
        custom_agents[agent_id] = {
            "agentId": agent_id,
            "url": agent_url,
            "custom_name": custom_name,
            "agent_card": agent_card,
            "added_timestamp": datetime.now().isoformat(),
            "type": "custom"
        }
        
        # Also register it in the main agents registry
        registered_agents[agent_id] = AgentInfo(
            agentId=agent_id,
            name=agent_name,
            type="custom",
            status="unknown",  # Will be checked in background
            capabilities=[], # Will be populated from agent card if available
            lastActivity=datetime.now().isoformat(),
            currentClaims=[]
        )
        
        # Store agent card for detailed view
        agent_cards[agent_id] = agent_card
        
        # Save to file
        save_custom_agents()
        
        # Check agent health in background
        asyncio.create_task(check_and_update_custom_agent_status(agent_id))
        
        terminal_logger.log("SUCCESS", "CUSTOM_AGENT", f"Added custom agent: {agent_name} ({agent_url})")
        
        return {
            "success": True,
            "message": f"Successfully added agent: {agent_name}",
            "agentId": agent_id,
            "agentName": agent_name,
            "status": "Agent added successfully. Status will be updated automatically.",
            "offline_reason": agent_card.get("offline_reason") if agent_card.get("offline_reason") else None
        }
        
    except Exception as e:
        terminal_logger.log("ERROR", "CUSTOM_AGENT", f"Failed to add custom agent: {e}")
        return {"success": False, "error": f"Internal error: {str(e)}"}

@app.delete("/api/agents/{agent_id}")
async def remove_custom_agent(agent_id: str):
    """Remove a custom agent"""
    try:
        # Check if it's a built-in agent (protect them)
        built_in_agents = ["claims_orchestrator", "intake_clarifier", "document_intelligence", "coverage_rules_engine"]
        if agent_id in built_in_agents:
            return {"success": False, "error": "Cannot remove built-in agents"}
        
        # Check if agent exists in custom agents
        if agent_id not in custom_agents:
            return {"success": False, "error": "Custom agent not found"}
        
        # Get agent name for logging
        agent_info = custom_agents[agent_id]
        agent_name = agent_info.get("agent_card", {}).get("name", agent_id)
        
        # Remove from all registries
        del custom_agents[agent_id]
        
        if agent_id in registered_agents:
            del registered_agents[agent_id]
        
        if agent_id in agent_cards:
            del agent_cards[agent_id]
        
        # Save to file
        save_custom_agents()
        
        terminal_logger.log("SUCCESS", "CUSTOM_AGENT", f"Removed custom agent: {agent_name}")
        
        return {
            "success": True,
            "message": f"Successfully removed agent: {agent_name}"
        }
        
    except Exception as e:
        terminal_logger.log("ERROR", "CUSTOM_AGENT", f"Failed to remove custom agent: {e}")
        return {"success": False, "error": f"Internal error: {str(e)}"}

async def check_and_update_custom_agent_status(agent_id: str):
    """Check and update status for a custom agent"""
    if agent_id not in custom_agents:
        return
    
    agent_url = custom_agents[agent_id]["url"]
    status = await check_real_agent_health(agent_url, agent_id)
    
    if agent_id in registered_agents:
        registered_agents[agent_id].status = status
        registered_agents[agent_id].lastActivity = datetime.now().isoformat()
        
        terminal_logger.log("INFO", "CUSTOM_AGENT", f"Updated status for {agent_id}: {status}")

@app.post("/api/email-notification")
async def receive_email_notification(request: Request):
    """Receive email notification from Communication Agent and broadcast to frontend"""
    try:
        data = await request.json()
        
        claim_id = data.get("claim_id", "Unknown")
        email_status = data.get("email_status", "unknown")
        details = data.get("details", {})
        
        terminal_logger.log("EMAIL", "NOTIFICATION", f"📧 Email notification received: {email_status} for claim {claim_id}")
        
        # Send real-time notification to all connected clients
        await notification_manager.send_email_notification(claim_id, email_status, details)
        
        # Log the notification
        notification_log = {
            "timestamp": datetime.now().isoformat(),
            "claim_id": claim_id,
            "email_status": email_status,
            "details": details
        }
        
        return {
            "success": True,
            "message": f"Email notification processed for claim {claim_id}",
            "notification": notification_log
        }
        
    except Exception as e:
        terminal_logger.log("ERROR", "EMAIL", f"Failed to process email notification: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/claims/{claim_id}/process")
async def process_claim(claim_id: str, request: ProcessingRequest, background_tasks: BackgroundTasks):
    """Start claim processing with integrated session management"""
    if claim_id not in active_claims:
        terminal_logger.log("ERROR", "API", f"Cannot process - claim not found: {claim_id}")
        raise HTTPException(status_code=404, detail="Claim not found")
    
    # STEP 1: Start processing session for real-time steps tracking
    terminal_logger.log("INFO", "PROCESS", f"🚀 AUTO-STARTING processing session for claim: {claim_id}")
    start_claim_processing_session(claim_id)
    global current_viewing_claim
    current_viewing_claim = claim_id
    
    # Update claim status
    active_claims[claim_id].status = "processing"
    active_claims[claim_id].assignedEmployee = request.employeeId
    active_claims[claim_id].lastUpdate = datetime.now().isoformat()
    
    terminal_logger.log("CLAIM", "PROCESS", f"Started processing claim: {claim_id} by employee: {request.employeeId}")
    
    # Start background processing simulation
    background_tasks.add_task(simulate_claim_processing_with_session, claim_id)
    
    return {"message": f"Processing started for claim {claim_id}", "status": "processing"}

async def simulate_claim_processing_with_session(claim_id: str):
    """Enhanced background processing with session cleanup"""
    try:
        # Call the original processing simulation
        await simulate_claim_processing(claim_id)
        
        # Wait a bit longer for all workflow steps to complete
        await asyncio.sleep(5)
        
        # STEP 2: Auto-stop processing session after workflow completion
        terminal_logger.log("INFO", "PROCESS", f"🏁 AUTO-STOPPING processing session for claim: {claim_id}")
        end_claim_processing_session(claim_id)
        
        # Clear viewing claim if it matches
        global current_viewing_claim
        if current_viewing_claim == claim_id:
            current_viewing_claim = None
            
        terminal_logger.log("SUCCESS", "PROCESS", f"✅ Completed processing with session cleanup for claim: {claim_id}")
        
    except Exception as e:
        terminal_logger.log("ERROR", "PROCESS", f"❌ Error in processing with session for {claim_id}: {str(e)}")
        # Ensure session cleanup on error
        end_claim_processing_session(claim_id)

@app.get("/api/logs")
async def get_processing_logs():
    """Get recent processing logs"""
    return {"logs": processing_logs[-50:]}  # Return last 50 logs

# Global storage for real-time workflow steps
live_workflow_steps = []

# Add some test steps when the app starts
live_workflow_steps.append({
    'id': 'test_001',
    'claim_id': 'TEST',
    'title': '🧪 Test Step',
    'description': 'Dashboard workflow system initialized',
    'status': 'completed',
    'timestamp': datetime.now().isoformat(),
    'step_type': 'system'
})

def parse_workflow_steps_from_logs(orchestrator_response: str, claim_id: str) -> List[Dict[str, Any]]:
    """Parse workflow steps from orchestrator terminal logs"""
    steps = []
    lines = orchestrator_response.split('\n')
    
    step_patterns = [
        (r'🔍 STEP 1: AGENT DISCOVERY PHASE', '🔍 Agent Discovery', 'Starting agent discovery process...'),
        (r'🎯 DISCOVERY COMPLETE: Found (\d+) agents online', '✅ Discovery Complete', lambda m: f'Found {m.group(1)} agents online'),
        (r'🔍 STEP 2: CHECKING EXISTING CLAIM DATA', '📋 Data Check', 'Checking existing claim data in database'),
        (r'📝 STEP 3A: INTAKE CLARIFICATION TASK', '📝 Intake Task', 'Starting intake clarification process'),
        (r'🎯 AGENT SELECTION: Selecting agent for task type \'([^\']+)\'', '🎯 Agent Selection', lambda m: f'Selecting agent for {m.group(1)}'),
        (r'✅ Direct match: ([a-z_]+) handles ([a-z_]+)', '✅ Agent Match', lambda m: f'Selected {m.group(1)} for {m.group(2)}'),
        (r'📤 TASK DISPATCH: Sending task to ([a-z_]+)', '📤 Task Dispatch', lambda m: f'Dispatching task to {m.group(1)}'),
        (r'✅ TASK SUCCESS: ([a-z_]+) processed task successfully', '✅ Task Success', lambda m: f'{m.group(1)} completed task successfully'),
        (r'⚖️ STEP 3C: COVERAGE VALIDATION TASK', '⚖️ Coverage Task', 'Starting coverage validation process'),
        (r'🎯 STEP 4: MAKING FINAL DECISION', '🎯 Final Decision', 'Analyzing results for final decision'),
        (r'✅ Decision: ([A-Z]+) - (.+)', '✅ Decision Made', lambda m: f'Decision: {m.group(1)} - {m.group(2)}'),
        (r'💾 STEP 5: STORING RESULTS TO COSMOS DB', '💾 Storage', 'Storing results to database'),
        (r'🎉 CLAIM ([A-Z0-9_]+) PROCESSING COMPLETED SUCCESSFULLY', '🎉 Complete', lambda m: f'Claim {m.group(1)} processing completed'),
    ]
    
    step_counter = 1
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        for pattern, title, description in step_patterns:
            import re
            match = re.search(pattern, line)
            if match:
                if callable(description):
                    desc = description(match)
                else:
                    desc = description
                
                steps.append({
                    'id': f'step_{step_counter:03d}',
                    'claim_id': claim_id,
                    'title': title,
                    'description': desc,
                    'status': 'completed',
                    'timestamp': datetime.now().isoformat(),
                    'step_type': 'workflow',
                    'raw_line': line
                })
                step_counter += 1
                break
    
    return steps

@app.post("/api/workflow-step")
async def receive_workflow_step(step_data: dict):
    """Receive workflow step from claims orchestrator"""
    live_workflow_steps.append({
        **step_data,
        "timestamp": datetime.now().isoformat(),
        "id": f"step_{len(live_workflow_steps)+1:03d}"
    })
    
    # Keep only last 100 steps
    if len(live_workflow_steps) > 100:
        live_workflow_steps.pop(0)
    
    terminal_logger.log("WORKFLOW", "STEP", f"Received: {step_data.get('title', 'Unknown step')}")
    return {"status": "received"}

@app.get("/api/live-processing-steps")
async def get_live_processing_steps():
    """Get real-time processing steps"""
    return {"steps": live_workflow_steps[-20:]}  # Return last 20 steps

@app.get("/api/processing-steps/{claim_id}")
async def get_processing_steps(claim_id: str):
    """Get processing steps for a specific claim"""
    try:
        # First try to get real workflow steps from orchestrator
        real_steps = workflow_logger.get_workflow_steps(claim_id)
        if real_steps:
            terminal_logger.log("DEBUG", "API", f"Returning {len(real_steps)} real workflow steps for claim {claim_id}")
            return {"claim_id": claim_id, "steps": real_steps}
        
        # Fallback to live steps for backward compatibility
        claim_steps = [step for step in live_workflow_steps if step.get('claim_id') == claim_id]
        if claim_steps:
            terminal_logger.log("DEBUG", "API", f"Returning {len(claim_steps)} live workflow steps for claim {claim_id}")
            return {"claim_id": claim_id, "steps": claim_steps}
        
        terminal_logger.log("WARNING", "API", f"No workflow steps found for claim {claim_id}")
        return {"claim_id": claim_id, "steps": []}
        
    except Exception as e:
        terminal_logger.log("ERROR", "API", f"Error getting workflow steps for {claim_id}: {str(e)}")
        return {"claim_id": claim_id, "steps": []}

@app.get("/api/recent-workflow-steps")
async def get_recent_workflow_steps():
    """Get recent workflow steps from the last 2 processing runs"""
    try:
        terminal_logger.log("DEBUG", "API", "🔍 Recent workflow steps requested")
        
        # Force refresh from file to get latest data
        workflow_logger._load_from_file()
        
        # Get recent steps from all claims, limited to last 2 runs
        recent_steps = workflow_logger.get_all_recent_steps(limit=20)
        
        if recent_steps:
            # Group by claim_id to get last 2 unique claims
            claims_seen = set()
            filtered_steps = []
            
            for step in recent_steps:
                claim_id = step.get('claim_id')
                if claim_id and len(claims_seen) < 2:
                    if claim_id not in claims_seen:
                        claims_seen.add(claim_id)
                    filtered_steps.append(step)
                elif claim_id in claims_seen:
                    filtered_steps.append(step)
            
            # Limit to reasonable number of steps
            filtered_steps = filtered_steps[:15]
            
            terminal_logger.log("DEBUG", "API", f"   Retrieved {len(filtered_steps)} recent steps from {len(claims_seen)} recent claims")
            return {
                "steps": filtered_steps,
                "total_steps": len(filtered_steps),
                "claims_count": len(claims_seen),
                "status": "success"
            }
        else:
            terminal_logger.log("DEBUG", "API", "   No recent workflow steps found")
            return {
                "steps": [],
                "total_steps": 0,
                "claims_count": 0,
                "status": "no_data"
            }
            
    except Exception as e:
        terminal_logger.log("ERROR", "API", f"Error getting recent workflow steps: {str(e)}")
        return {
            "steps": [],
            "total_steps": 0,
            "claims_count": 0,
            "status": "error",
            "error": str(e)
        }

@app.get("/api/workflow-history/{claim_id}")
async def get_workflow_history(claim_id: str):
    """Get complete workflow history for a specific claim"""
    try:
        terminal_logger.log("DEBUG", "API", f"🔍 Workflow history requested for claim: {claim_id}")
        
        # Force refresh from file to get latest data
        workflow_logger._load_from_file()
        
        # Get all steps for this claim
        claim_steps = workflow_logger.get_workflow_steps(claim_id)
        
        if claim_steps:
            terminal_logger.log("DEBUG", "API", f"   Retrieved {len(claim_steps)} workflow steps for {claim_id}")
            return {
                "claim_id": claim_id,
                "steps": claim_steps,
                "total_steps": len(claim_steps),
                "status": "success"
            }
        else:
            terminal_logger.log("DEBUG", "API", f"   No workflow steps found for {claim_id}")
            return {
                "claim_id": claim_id,
                "steps": [],
                "total_steps": 0,
                "status": "no_data"
            }
            
    except Exception as e:
        terminal_logger.log("ERROR", "API", f"Error getting workflow history for {claim_id}: {str(e)}")
        return {
            "claim_id": claim_id,
            "steps": [],
            "total_steps": 0,
            "status": "error",
            "error": str(e)
        }

# ============= DYNAMIC WORKFLOW API PROXY ROUTES =============
# Proxy routes to forward requests to Claims Orchestrator API at localhost:8001

@app.get("/workflow-steps")
async def proxy_get_all_workflows():
    """Proxy route: Get all workflows from Claims Orchestrator"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8001/workflow-steps") as response:
                if response.status == 200:
                    data = await response.json()
                    terminal_logger.log("SUCCESS", "PROXY", f"Retrieved workflows from orchestrator: {len(data.get('workflows', {}))} sessions")
                    return data
                else:
                    terminal_logger.log("ERROR", "PROXY", f"Orchestrator API returned {response.status}")
                    return {"workflows": {}}
    except Exception as e:
        terminal_logger.log("ERROR", "PROXY", f"Failed to connect to orchestrator: {str(e)}")
        return {"workflows": {}}

@app.get("/workflow-steps/{session_id}")
async def proxy_get_session_workflows(session_id: str):
    """Proxy route: Get workflow steps for specific session from Claims Orchestrator"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:8001/workflow-steps/{session_id}") as response:
                if response.status == 200:
                    data = await response.json()
                    steps = data.get("steps", [])
                    terminal_logger.log("SUCCESS", "PROXY", f"Retrieved {len(steps)} steps for session {session_id[:8]}...")
                    return data
                else:
                    terminal_logger.log("ERROR", "PROXY", f"Orchestrator API returned {response.status} for session {session_id}")
                    return {"steps": [], "session_id": session_id}
    except Exception as e:
        terminal_logger.log("ERROR", "PROXY", f"Failed to get session {session_id} from orchestrator: {str(e)}")
        return {"steps": [], "session_id": session_id}

# ============= END DYNAMIC WORKFLOW API PROXY =============

@app.get("/api/processing-steps") 
async def get_all_processing_steps():
    """Get real-time processing steps for actively processing claims"""
    try:
        terminal_logger.log("DEBUG", "API", "🔍 Processing steps API called")
        terminal_logger.log("DEBUG", "API", f"   Current processing claims: {list(current_processing_claims)}")
        terminal_logger.log("DEBUG", "API", f"   Active sessions count: {len(current_processing_claims)}")
        
        # Get real-time steps with proper claim filtering
        active_steps = get_real_time_processing_steps()
        active_sessions_count = len(current_processing_claims)
        
        terminal_logger.log("DEBUG", "API", f"   Retrieved {len(active_steps)} active steps")
        
        if active_steps:
            # Convert step objects to dictionaries for JSON response
            steps_data = []
            for step in active_steps:
                if hasattr(step, 'to_dict'):
                    # WorkflowStep object
                    step_dict = step.to_dict()
                else:
                    # Already a dictionary
                    step_dict = step
                
                # Fix the details display issue
                if isinstance(step_dict.get('details'), dict):
                    # Convert complex objects to readable strings
                    details_str = []
                    for key, value in step_dict['details'].items():
                        if isinstance(value, (list, dict)):
                            details_str.append(f"{key}: {str(value)}")
                        else:
                            details_str.append(f"{key}: {value}")
                    step_dict['details_display'] = "; ".join(details_str)
                else:
                    step_dict['details_display'] = str(step_dict.get('details', ''))
                
                steps_data.append(step_dict)
            
            terminal_logger.log("DEBUG", "API", f"✅ Returning {len(steps_data)} real-time steps for {active_sessions_count} active claims")
            
            return {
                "steps": steps_data,
                "active_sessions": active_sessions_count,
                "processing_claims": list(current_processing_claims)
            }
        else:
            terminal_logger.log("DEBUG", "API", f"❌ No active processing steps (active claims: {active_sessions_count})")
            return {
                "steps": [],
                "active_sessions": active_sessions_count,
                "processing_claims": list(current_processing_claims)
            }
            
    except Exception as e:
        terminal_logger.log("ERROR", "API", f"❌ Error getting real-time processing steps: {str(e)}")
        import traceback
        terminal_logger.log("ERROR", "API", f"   Traceback: {traceback.format_exc()}")
        return {
            "steps": [],
            "active_sessions": 0,
            "processing_claims": [],
            "error": str(e)
        }

@app.get("/api/workflow-history/{claim_id}")
async def get_workflow_history(claim_id: str):
    """Get complete workflow history for a specific claim"""
    try:
        terminal_logger.log("DEBUG", "API", f"🔍 Workflow history requested for claim: {claim_id}")
        
        # Force reload from file to get latest data
        workflow_logger._load_from_file()
        
        # Get steps for the specific claim
        claim_steps = workflow_logger.get_workflow_steps(claim_id)
        
        terminal_logger.log("DEBUG", "API", f"   Retrieved {len(claim_steps)} workflow steps for {claim_id}")
        
        if claim_steps:
            # Sort steps by timestamp to show proper chronological order
            sorted_steps = sorted(claim_steps, key=lambda x: x.get('timestamp', ''))
            
            terminal_logger.log("DEBUG", "API", f"✅ Returning workflow history for {claim_id}")
            return {
                "claim_id": claim_id,
                "steps": sorted_steps,
                "total_steps": len(sorted_steps),
                "has_history": True
            }
        else:
            terminal_logger.log("DEBUG", "API", f"❌ No workflow history found for {claim_id}")
            return {
                "claim_id": claim_id,
                "steps": [],
                "total_steps": 0,
                "has_history": False
            }
            
    except Exception as e:
        terminal_logger.log("ERROR", "API", f"Error getting workflow history for {claim_id}: {str(e)}")
        return {
            "claim_id": claim_id,
            "steps": [],
            "total_steps": 0,
            "has_history": False,
            "error": str(e)
        }

@app.post("/api/start-processing/{claim_id}")
async def start_processing_claim(claim_id: str):
    """Start processing a specific claim and show its steps"""
    try:
        global current_viewing_claim
        terminal_logger.log("INFO", "PROCESSING", f"🚀 Starting processing session for claim: {claim_id}")
        
        start_claim_processing_session(claim_id)
        current_viewing_claim = claim_id
        
        terminal_logger.log("INFO", "PROCESSING", f"✅ Session started for claim {claim_id}")
        terminal_logger.log("DEBUG", "PROCESSING", f"   Current processing claims: {list(current_processing_claims)}")
        terminal_logger.log("DEBUG", "PROCESSING", f"   Active sessions: {len(current_processing_claims)}")
        
        return {
            "status": "success",
            "message": f"Started processing claim {claim_id}",
            "claim_id": claim_id,
            "session_active": True
        }
    except Exception as e:
        terminal_logger.log("ERROR", "PROCESSING", f"❌ Error starting processing for {claim_id}: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/api/stop-processing/{claim_id}")
async def stop_processing_claim(claim_id: str):
    """Stop processing a specific claim and clear its steps"""
    try:
        global current_viewing_claim
        end_claim_processing_session(claim_id)
        
        if current_viewing_claim == claim_id:
            current_viewing_claim = None
            
        terminal_logger.log("INFO", "PROCESSING", f"Stopped processing for claim {claim_id}")
        return {
            "status": "success", 
            "message": f"Stopped processing claim {claim_id}",
            "claim_id": claim_id,
            "session_active": False
        }
    except Exception as e:
        terminal_logger.log("ERROR", "PROCESSING", f"Error stopping processing for {claim_id}: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/api/processing-status")
async def get_processing_status():
    """Get current processing status and active sessions"""
    return {
        "active_sessions": active_processing_sessions,
        "current_viewing_claim": current_viewing_claim,
        "sessions_count": len([s for s in active_processing_sessions.values() if s["status"] == "processing"])
    }

@app.get("/api/debug-workflow-connection")
async def debug_workflow_connection():
    """Debug endpoint to verify real workflow logger connection"""
    try:
        # Test workflow logger functionality  
        test_claim_id = f"TEST_{datetime.now().strftime('%H%M%S')}"
        workflow_logger.start_claim_processing(test_claim_id)
        
        step_id = workflow_logger.add_step(
            step_type=WorkflowStepType.DISCOVERY,  # Need to import this
            title="🧪 Connection Test",
            description="Testing dashboard connection to real workflow logger",
            status=WorkflowStepStatus.COMPLETED
        )
        
        # Get the test step back
        test_steps = workflow_logger.get_workflow_steps(test_claim_id)
        all_recent = workflow_logger.get_all_recent_steps(5)
        
        return {
            "connection_status": "SUCCESS",
            "workflow_logger_type": type(workflow_logger).__name__,
            "test_claim_id": test_claim_id,
            "test_step_created": step_id,
            "test_steps_retrieved": len(test_steps),
            "recent_steps_available": len(all_recent),
            "sample_test_step": test_steps[0] if test_steps else None,
            "storage_file_exists": str(workflow_logger.storage_file.exists()),
            "storage_file_path": str(workflow_logger.storage_file)
        }
    except Exception as e:
        return {
            "connection_status": "ERROR",
            "error": str(e),
            "workflow_logger_type": type(workflow_logger).__name__,
        }

async def simulate_claim_processing(claim_id: str):
    """Process claim using REAL A2A agents instead of simulation"""
    try:
        terminal_logger.log("CLAIM", "WORKFLOW", f"Starting REAL agent processing for {claim_id}")
        
        # Immediately add a start step to see if the live_workflow_steps is working
        live_workflow_steps.append({
            'id': f'start_{claim_id}',
            'claim_id': claim_id,
            'title': '🚀 Processing Started',
            'description': f'Starting claim processing for {claim_id}',
            'status': 'in_progress',
            'timestamp': datetime.now().isoformat(),
            'step_type': 'start'
        })
        terminal_logger.log("DEBUG", "WORKFLOW", f"Added start step. Total steps: {len(live_workflow_steps)}")
        
        # Get the actual claim data
        claim_data = active_claims.get(claim_id)
        if not claim_data:
            terminal_logger.log("ERROR", "WORKFLOW", f"Claim data not found for {claim_id}")
            return
        
        # Convert claim data to proper format  
        claim_info = {
            "claim_id": claim_id,
            "type": claim_data.category.lower() if claim_data.category else "outpatient",
            "amount": float(claim_data.amountBilled),
            "description": f"Insurance claim processing for {claim_id}",
            "customer_id": claim_data.assignedEmployee or "emp23", 
            "policy_number": f"POL_{claim_id}",
            "incident_date": "2024-01-15",
            "location": "Dashboard Processing", 
            "documents": ["claim_form.pdf", "supporting_documents.pdf"],
            "customer_statement": f"Processing {claim_data.category} claim through dashboard interface",
            # Include additional fields for proper processing
            "patient_name": claim_data.patientName or f"Patient-{claim_id}",
            "provider": claim_data.provider or "Unknown Provider",
            "member_id": claim_data.memberId or "Unknown", 
            "region": claim_data.region or "US"
        }
        
        # Send to real orchestrator using A2A protocol
        a2a_payload = {
            "jsonrpc": "2.0",
            "id": f"dashboard-{claim_id}-{datetime.now().strftime('%H%M%S')}",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"msg-{claim_id}-{datetime.now().strftime('%H%M%S')}",
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": json.dumps({
                                "action": "process_claim",
                                "claim_id": claim_id,
                                "claim_data": claim_info
                            })
                        }
                    ]
                }
            }
        }
        
        terminal_logger.log("AGENT", "CALL", f"Sending claim {claim_id} to real orchestrator...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001",  # orchestrator URL
                json=a2a_payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=60)  # Allow more time for real processing
            ) as response:
                
                response_text = await response.text()
                
                # Parse workflow steps from orchestrator logs (if it contains log data)
                # Note: In a real implementation, we might capture orchestrator stdout,
                # but for now we'll parse from response and generate steps
                if response.status < 400:
                    terminal_logger.log("SUCCESS", "AGENT", f"Successfully sent claim {claim_id} to orchestrator")
                    terminal_logger.log("AGENT", "RESPONSE", f"Orchestrator processing claim {claim_id}")
                    
                    # IMPORTANT: No longer generate fake workflow steps here!
                    # The real workflow steps are captured by the orchestrator's workflow_logger
                    # and served through the workflow_logger.get_all_recent_steps() API
                    
                    try:
                        # Parse the actual response from the enhanced orchestrator
                        response_json = json.loads(response_text)
                        result = response_json.get('result', {})
                        
                        # Extract the real decision from orchestrator
                        final_decision = result.get('final_decision', {})
                        decision = final_decision.get('decision', 'unknown')
                        reasoning = final_decision.get('reasoning', 'No reasoning provided')
                        confidence = final_decision.get('confidence', 0)
                        
                        # Update claim with actual orchestrator results  
                        if decision == 'approved':
                            active_claims[claim_id].status = "approved"
                        elif decision == 'denied':
                            active_claims[claim_id].status = "denied"
                        elif decision == 'requires_review':
                            active_claims[claim_id].status = "pending"
                        else:
                            active_claims[claim_id].status = "completed"
                            
                        active_claims[claim_id].lastUpdate = datetime.now().isoformat()
                        
                        # Log the actual results to Recent Activity
                        terminal_logger.log("SUCCESS", "DECISION", f"Claim {claim_id}: {decision.upper()}")
                        terminal_logger.log("REASONING", "DECISION", f"Reasoning: {reasoning}")
                        terminal_logger.log("CONFIDENCE", "DECISION", f"Confidence: {confidence:.0%}")
                        
                        # No longer add hardcoded final steps - use real workflow logger data!
                        
                        # Log processing steps if available
                        processing_steps = result.get('processing_steps', [])
                        if processing_steps:
                            terminal_logger.log("STEPS", "WORKFLOW", f"Processing steps: {', '.join(processing_steps)}")
                        
                        # Log agents used
                        agents_used = result.get('agents_used', [])
                        if agents_used:
                            terminal_logger.log("AGENTS", "WORKFLOW", f"Agents used: {', '.join(agents_used)}")
                            
                        terminal_logger.log("SUCCESS", "WORKFLOW", f"Claim {claim_id} processing completed - {decision.upper()}")
                        
                    except (json.JSONDecodeError, KeyError) as e:
                        terminal_logger.log("WARNING", "PARSING", f"Could not parse orchestrator response: {str(e)}")
                        # Fallback - just mark as completed
                        active_claims[claim_id].status = "completed"
                        active_claims[claim_id].lastUpdate = datetime.now().isoformat()
                        terminal_logger.log("SUCCESS", "WORKFLOW", f"Claim {claim_id} processing completed by real agents")
                    
                else:
                    terminal_logger.log("ERROR", "AGENT", f"Orchestrator error {response.status}: {response_text}")
                    active_claims[claim_id].status = "error"
                    active_claims[claim_id].lastUpdate = datetime.now().isoformat()
        
    except Exception as e:
        terminal_logger.log("ERROR", "WORKFLOW", f"Real agent processing failed for {claim_id}: {str(e)}")
        active_claims[claim_id].status = "error"
        active_claims[claim_id].lastUpdate = datetime.now().isoformat()

# ============= CHAT FUNCTIONALITY =============

@app.post("/api/chat")
async def chat_with_orchestrator(chat_request: ChatMessage):
    """Enhanced chat with integrated UI orchestrator for complete claim processing workflow"""
    try:
        terminal_logger.log("CHAT", "MESSAGE", f"Session {chat_request.sessionId[:8]}...: {chat_request.message[:50]}...")
        
        # Initialize session if not exists
        if chat_request.sessionId not in chat_sessions:
            chat_sessions[chat_request.sessionId] = []
        
        # Store user message
        chat_sessions[chat_request.sessionId].append({
            "role": "user",
            "content": chat_request.message,
            "timestamp": chat_request.timestamp
        })
        
        # Try to use our integrated orchestrator first (for claim processing)
        if ORCHESTRATOR_AVAILABLE:
            try:
                terminal_logger.log("CHAT", "ORCHESTRATOR", "Using intelligent orchestrator for enhanced workflow...")
                
                # Create orchestrator instance and process the message
                orchestrator = IntelligentClaimsOrchestrator()
                await orchestrator.initialize()
                
                orchestrator_response = await orchestrator._process_intelligent_request(
                    user_input=chat_request.message,
                    session_id=chat_request.sessionId
                )
                
                # Store assistant response
                chat_sessions[chat_request.sessionId].append({
                    "role": "assistant",
                    "content": orchestrator_response.get("message", ""),
                    "timestamp": datetime.now().isoformat(),
                    "status": orchestrator_response.get("status", "unknown"),
                    "claim_id": orchestrator_response.get("claim_id"),
                    "requires_confirmation": orchestrator_response.get("type") == "awaiting_confirmation",
                    "final_decision": orchestrator_response.final_decision
                })
                
                terminal_logger.log("SUCCESS", "CHAT", f"UI orchestrator response: {orchestrator_response.status}")
                
                return ChatResponse(
                    response=orchestrator_response.message,  # Map message to response
                    sessionId=chat_request.sessionId,
                    timestamp=datetime.now().isoformat(),
                    status=orchestrator_response.status,
                    claim_id=orchestrator_response.claim_id,
                    requires_confirmation=orchestrator_response.requires_confirmation or False,
                    final_decision=orchestrator_response.final_decision
                )
                
            except Exception as e:
                terminal_logger.log("WARNING", "CHAT", f"UI orchestrator failed, falling back to legacy chat: {e}")
                # Fall through to legacy implementation
        
        # Legacy implementation as fallback
        
        # Prepare A2A payload for Claims Orchestrator with proper JSON-RPC 2.0 format
        a2a_payload = {
            "jsonrpc": "2.0",
            "id": f"chat-{chat_request.sessionId}-{uuid.uuid4()}",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"msg-{uuid.uuid4()}",
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": f"Chat Query: {chat_request.message}"
                        }
                    ]
                },
                "context_id": f"chat_{chat_request.sessionId}",
                "message_id": f"msg-{uuid.uuid4()}"
            }
        }
        
        terminal_logger.log("CHAT", "ORCHESTRATOR", "Forwarding chat message to Claims Orchestrator...")
        
        # Send to Claims Orchestrator
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001",  # Claims Orchestrator URL
                json=a2a_payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=600)  # 10 minutes - allow for complex claim processing
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    
                    # Extract response text from A2A response - improved parsing for JSON-RPC wrapper
                    orchestrator_response = "I'm here to help! However, I couldn't process your request at the moment."
                    
                    if isinstance(result, dict):
                        # Handle JSON-RPC wrapper format first (most common from orchestrator)
                        if "result" in result and isinstance(result["result"], dict):
                            json_rpc_result = result["result"]
                            
                            # Extract text from parts array structure
                            if "parts" in json_rpc_result and isinstance(json_rpc_result["parts"], list):
                                for part in json_rpc_result["parts"]:
                                    if isinstance(part, dict) and part.get("kind") == "text" and "text" in part:
                                        orchestrator_response = part["text"]
                                        break
                            # Fallback: check for direct message in result
                            elif "message" in json_rpc_result:
                                orchestrator_response = json_rpc_result["message"]
                            elif isinstance(json_rpc_result, str):
                                orchestrator_response = json_rpc_result
                        
                        # Handle other A2A response formats
                        elif "artifacts" in result and result["artifacts"]:
                            # A2A response with artifacts
                            first_artifact = result["artifacts"][0]
                            if "content" in first_artifact:
                                orchestrator_response = first_artifact["content"]
                        elif "messages" in result and result["messages"]:
                            # A2A response with messages
                            for msg in result["messages"]:
                                if msg.get("role") == "assistant" and "content" in msg:
                                    orchestrator_response = msg["content"]
                                    break
                        elif "response" in result:
                            orchestrator_response = result["response"]
                        elif "content" in result:
                            orchestrator_response = result["content"] 
                        elif "message" in result:
                            orchestrator_response = result["message"]
                        elif "result" in result and isinstance(result["result"], str):
                            orchestrator_response = result["result"]
                        else:
                            # Try to extract from common A2A response patterns
                            if "taskId" in result or "contextId" in result:
                                # This looks like an A2A response, try to extract meaningful content
                                orchestrator_response = f"I processed your request about: '{chat_request.message}'. The system is working on it."
                            else:
                                # Fallback: Don't show raw JSON to user
                                orchestrator_response = "I processed your request, but the response format was unexpected. Please try rephrasing your question."
                    elif isinstance(result, str):
                        # Direct string response
                        orchestrator_response = result
                    
                    # Store assistant response
                    chat_sessions[chat_request.sessionId].append({
                        "role": "assistant", 
                        "content": orchestrator_response,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    terminal_logger.log("CHAT", "SUCCESS", f"Response sent for session {chat_request.sessionId[:8]}...")
                    
                    return ChatResponse(
                        response=orchestrator_response,
                        sessionId=chat_request.sessionId,
                        timestamp=datetime.now().isoformat()
                    )
                    
                else:
                    error_text = await response.text()
                    terminal_logger.log("CHAT", "ERROR", f"Orchestrator returned {response.status}: {error_text[:100]}...")
                    
                    error_response = f"Sorry, I'm having trouble connecting to the Claims Orchestrator (Status: {response.status}). Please make sure the orchestrator is running on port 8001 and try again."
                    
                    chat_sessions[chat_request.sessionId].append({
                        "role": "assistant",
                        "content": error_response,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    return ChatResponse(
                        response=error_response,
                        sessionId=chat_request.sessionId,
                        timestamp=datetime.now().isoformat()
                    )
                    
    except aiohttp.ClientError as e:
        terminal_logger.log("CHAT", "ERROR", f"Connection error: {str(e)}")
        error_response = f"I'm unable to connect to the Claims Orchestrator. Please ensure it's running on port 8001. Error: {str(e)}"
        
        # Store error response
        if chat_request.sessionId in chat_sessions:
            chat_sessions[chat_request.sessionId].append({
                "role": "assistant",
                "content": error_response,
                "timestamp": datetime.now().isoformat()
            })
        
        return ChatResponse(
            response=error_response,
            sessionId=chat_request.sessionId,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        terminal_logger.log("CHAT", "ERROR", f"Chat processing failed: {str(e)}")
        error_response = f"Sorry, I encountered an unexpected error: {str(e)}. Please try again."
        
        # Store error response
        if chat_request.sessionId in chat_sessions:
            chat_sessions[chat_request.sessionId].append({
                "role": "assistant",
                "content": error_response,
                "timestamp": datetime.now().isoformat()
            })
        
        return ChatResponse(
            response=error_response,
            sessionId=chat_request.sessionId,
            timestamp=datetime.now().isoformat()
        )

@app.get("/api/chat/history/{session_id}")
async def get_chat_history(session_id: str):
    """Get chat history for a session"""
    if session_id in chat_sessions:
        return {"sessionId": session_id, "messages": chat_sessions[session_id]}
    return {"sessionId": session_id, "messages": []}

# ============= END CHAT FUNCTIONALITY =============

if __name__ == "__main__":
    terminal_logger.log("DASHBOARD", "START", "Starting Insurance Claims Processing Dashboard...")
    uvicorn.run(
        "app:app", 
        host="0.0.0.0", 
        port=3000, 
        reload=True,
        log_level="info"
    )
