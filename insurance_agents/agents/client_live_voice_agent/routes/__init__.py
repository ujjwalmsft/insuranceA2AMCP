"""Routes package"""

from .static_routes import router as static_router
from .a2a_routes import router as a2a_router, set_agent_card

__all__ = [
    'static_router',
    'a2a_router', 
    'set_agent_card'
]