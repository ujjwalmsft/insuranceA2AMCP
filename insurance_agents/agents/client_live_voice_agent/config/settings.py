"""
Application settings and configuration
"""

# Server configuration
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8007

# API configuration
API_TITLE = "Client Live Voice Agent"
API_DESCRIPTION = "A2A-compliant voice agent with Azure AI Foundry and Voice Live API integration"
API_VERSION = "1.0.0"

# CORS configuration
CORS_ORIGINS = ["*"]  # Allow all origins for development
CORS_CREDENTIALS = True
CORS_METHODS = ["*"]
CORS_HEADERS = ["*"]

# Agent configuration
AGENT_ID = "client_live_voice_agent"
AGENT_NAME = "ClientLiveVoiceAgent"
AGENT_URL = f"http://localhost:{SERVER_PORT}/"
AGENT_INPUT_MODES = ['audio', 'text']
AGENT_OUTPUT_MODES = ['audio', 'text']

# File paths
STATIC_HTML_FILE = "claims_voice_client.html"
STATIC_JS_FILES = {
    "claims_voice_client.js": "claims_voice_client.js",
    "audio-processor.js": "audio-processor.js", 
    "config.js": "config.js"
}

# Database configuration
DATABASE_QUERY_LIMIT = 10