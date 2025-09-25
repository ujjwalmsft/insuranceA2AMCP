"""Configuration package"""

from .settings import *
from .logging_config import setup_logging, get_logger

__all__ = [
    'SERVER_HOST', 'SERVER_PORT', 'API_TITLE', 'API_DESCRIPTION', 'API_VERSION',
    'CORS_ORIGINS', 'CORS_CREDENTIALS', 'CORS_METHODS', 'CORS_HEADERS',
    'AGENT_ID', 'AGENT_NAME', 'AGENT_URL', 'AGENT_INPUT_MODES', 'AGENT_OUTPUT_MODES',
    'STATIC_HTML_FILE', 'STATIC_JS_FILES', 'DATABASE_QUERY_LIMIT',
    'setup_logging', 'get_logger'
]