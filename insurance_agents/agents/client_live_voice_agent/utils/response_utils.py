"""
Utility functions for response handling
"""
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from pathlib import Path
from typing import Dict, Any
from config import get_logger

logger = get_logger(__name__)

def create_error_response(status_code: int, message: str, detail: str = None) -> JSONResponse:
    """Create standardized error response"""
    content = {"error": message}
    if detail:
        content["detail"] = detail
    return JSONResponse(status_code=status_code, content=content)

def create_success_response(data: Dict[str, Any]) -> JSONResponse:
    """Create standardized success response"""
    return JSONResponse(content=data)

def serve_static_file(file_path: Path, media_type: str, not_found_message: str = None) -> FileResponse:
    """Serve a static file with error handling"""
    try:
        if file_path.exists():
            return FileResponse(file_path, media_type=media_type)
        else:
            error_msg = not_found_message or f"{file_path.name} not found"
            logger.error(f"Static file not found: {file_path}")
            raise FileNotFoundError(error_msg)
    except Exception as e:
        logger.error(f"Error serving static file {file_path}: {e}")
        raise

def create_fallback_html(title: str, message: str, agent_card_url: str = None) -> HTMLResponse:
    """Create fallback HTML response"""
    agent_link = f'<p>Agent Card: <a href="{agent_card_url}">{agent_card_url}</a></p>' if agent_card_url else ""
    
    html_content = f"""
    <html>
    <head><title>{title}</title></head>
    <body>
        <h1>{title}</h1>
        <p>{message}</p>
        {agent_link}
    </body>
    </html>
    """
    return HTMLResponse(html_content)