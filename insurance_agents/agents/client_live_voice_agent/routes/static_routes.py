"""
Static file serving routes
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from config import STATIC_HTML_FILE, STATIC_JS_FILES, get_logger
from utils import serve_static_file, create_fallback_html

logger = get_logger(__name__)
router = APIRouter()

@router.get("/")
async def serve_voice_interface():
    """Serve the voice client interface"""
    try:
        voice_client_path = Path(__file__).parent.parent / "static" / STATIC_HTML_FILE
        if voice_client_path.exists():
            return FileResponse(voice_client_path, media_type="text/html")
        else:
            return create_fallback_html(
                title="Voice Agent",
                message="Voice client interface not found. Please ensure claims_voice_client.html exists.",
                agent_card_url="/.well-known/agent.json"
            )
    except Exception as e:
        logger.error(f"Error serving voice interface: {e}")
        raise HTTPException(status_code=500, detail="Error serving interface")

@router.get("/claims_voice_client.js")
async def serve_claims_voice_client_js():
    """Serve the claims voice client JavaScript"""
    try:
        js_path = Path(__file__).parent.parent / "static" / STATIC_JS_FILES["claims_voice_client.js"]
        return serve_static_file(
            js_path, 
            "application/javascript",
            "Claims voice client JavaScript file not found"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Claims voice client JavaScript file not found")
    except Exception as e:
        logger.error(f"Error serving claims voice client JavaScript: {e}")
        raise HTTPException(status_code=500, detail="Error serving JavaScript")

@router.get("/audio-processor.js") 
async def serve_audio_processor_js():
    """Serve the audio processor JavaScript"""
    try:
        js_path = Path(__file__).parent.parent / "static" / STATIC_JS_FILES["audio-processor.js"]
        return serve_static_file(
            js_path,
            "application/javascript", 
            "Audio processor JavaScript file not found"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio processor JavaScript file not found")
    except Exception as e:
        logger.error(f"Error serving audio processor JavaScript: {e}")
        raise HTTPException(status_code=500, detail="Error serving JavaScript")

@router.get("/config.js")
async def serve_config_js():
    """Serve the configuration JavaScript"""
    try:
        config_path = Path(__file__).parent.parent / "static" / STATIC_JS_FILES["config.js"]
        return serve_static_file(
            config_path,
            "application/javascript",
            "Config file not found"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Config file not found")  
    except Exception as e:
        logger.error(f"Error serving config: {e}")
        raise HTTPException(status_code=500, detail="Error serving config")