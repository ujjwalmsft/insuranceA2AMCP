"""
Logging configuration for the voice agent
"""
import logging

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='🎤 [VOICE-AGENT-FASTAPI] %(asctime)s - %(levelname)s - %(message)s',
        datefmt="%H:%M:%S"
    )
    
    # Suppress verbose Azure client logging
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("azure.core").setLevel(logging.WARNING)
    logging.getLogger("azure.identity").setLevel(logging.WARNING)
    logging.getLogger("azure.ai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

def get_logger(name: str = __name__):
    """Get a logger instance"""
    return logging.getLogger(name)