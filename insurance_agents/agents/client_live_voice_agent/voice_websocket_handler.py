"""
Voice WebSocket Handler for real-time conversation tracking
Handles WebSocket connections from voice clients and logs conversations.
"""

import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect

# A2A imports for Azure thread storage (added safely)
try:
    from a2a.server.agent_execution import RequestContext
    from a2a.utils import new_agent_text_message
except ImportError:
    # If A2A imports fail, Azure thread storage will be skipped gracefully
    RequestContext = None
    new_agent_text_message = None

# Simple conversation tracker replacement
class SimpleTracker:
    def __init__(self):
        self.current_session_id = None
    
    def start_session(self, session_data):
        self.current_session_id = session_data.get('voice_session_id', 'default')
    
    def log_voice_interaction(self, *args, **kwargs): pass
    def log_agent_response(self, *args, **kwargs): pass
    def log_system_event(self, *args, **kwargs): pass
    def log_event(self, *args, **kwargs): pass
    def log_user_message(self, *args, **kwargs): pass
    def log_assistant_message(self, *args, **kwargs): pass
    def log_system_event(self, *args, **kwargs): pass

conversation_tracker = SimpleTracker()

class VoiceWebSocketHandler:
    """
    Handles WebSocket connections for voice clients
    Provides real-time conversation tracking and session management
    """
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.session_connections: Dict[str, str] = {}  # session_id -> connection_id
        self.logger = logging.getLogger(__name__)
        # Reference to voice executor for Azure thread storage (added safely)
        self.voice_executor = None
    
    async def connect(self, websocket: WebSocket, session_id: str = None) -> str:
        """
        Accept WebSocket connection and register it
        
        Args:
            websocket: WebSocket connection
            session_id: Optional session ID for conversation tracking
            
        Returns:
            Connection ID
        """
        await websocket.accept()
        
        connection_id = f"voice_conn_{datetime.now().timestamp()}"
        self.active_connections[connection_id] = websocket
        
        if session_id:
            self.session_connections[session_id] = connection_id
            
            # Start or resume conversation session
            if not conversation_tracker.current_session_id:
                conversation_tracker.start_session({
                    "connection_type": "websocket",
                    "connection_id": connection_id,
                    "voice_session_id": session_id,
                    "client_type": "voice_client"
                })
            
            conversation_tracker.log_system_event(
                event="WebSocket connection established",
                event_metadata={
                    "connection_id": connection_id,
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
        
        self.logger.info(f"🔌 Voice WebSocket connected: {connection_id}")
        return connection_id
    
    def disconnect(self, connection_id: str):
        """
        Handle WebSocket disconnection
        
        Args:
            connection_id: Connection ID to disconnect
        """
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            
            # Find and remove session connection
            session_id = None
            for sid, cid in list(self.session_connections.items()):
                if cid == connection_id:
                    session_id = sid
                    del self.session_connections[sid]
                    break
            
            conversation_tracker.log_system_event(
                event="WebSocket connection closed",
                event_metadata={
                    "connection_id": connection_id,
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            self.logger.info(f"🔌 Voice WebSocket disconnected: {connection_id}")
    
    async def handle_voice_message(self, websocket: WebSocket, connection_id: str):
        """
        Handle incoming voice messages from WebSocket
        
        Args:
            websocket: WebSocket connection
            connection_id: Connection ID
        """
        try:
            while True:
                # Receive message from WebSocket
                data = await websocket.receive_text()
                message = json.loads(data)
                
                await self._process_voice_message(message, connection_id)
                
        except WebSocketDisconnect:
            self.logger.info(f"🔌 WebSocket disconnected: {connection_id}")
            self.disconnect(connection_id)
        except Exception as e:
            self.logger.error(f"❌ Error handling voice message: {e}")
            await websocket.close(code=1011, reason="Internal error")
            self.disconnect(connection_id)
    
    async def _process_voice_message(self, message: Dict[str, Any], connection_id: str):
        """
        Process a voice message and log it to conversation tracker
        
        Args:
            message: Voice message from client
            connection_id: WebSocket connection ID
        """
        message_type = message.get("type", "unknown")
        
        if message_type == "session.created":
            # Voice session started
            session_id = message.get("session", {}).get("id")
            conversation_tracker.log_system_event(
                event="Voice session created",
                event_metadata={
                    "session_id": session_id,
                    "connection_id": connection_id,
                    "voice_session": message.get("session", {})
                }
            )
            
        elif message_type == "conversation.item.created":
            # New conversation item (user input or assistant response)
            item = message.get("item", {})
            item_type = item.get("type", "unknown")
            
            if item_type == "message":
                role = item.get("role", "unknown")
                content = self._extract_content_from_item(item)
                
                if role == "user":
                    # EXISTING: Log to conversation tracker (unchanged)
                    conversation_tracker.log_voice_interaction(
                        transcript=content,
                        audio_metadata={
                            "connection_id": connection_id,
                            "item_id": item.get("id"),
                            "voice_session": True
                        }
                    )
                    
                    # NEW: Also store in Azure AI thread (additive, non-breaking)
                    await self._store_in_azure_thread(content, self._get_session_id_for_connection(connection_id), connection_id)
                elif role == "assistant":
                    conversation_tracker.log_agent_response(
                        response=content,
                        response_metadata={
                            "connection_id": connection_id,
                            "item_id": item.get("id"),
                            "voice_session": True
                        }
                    )
                    
        elif message_type == "response.created":
            # Assistant response started
            response = message.get("response", {})
            conversation_tracker.log_system_event(
                event="Assistant response started",
                event_metadata={
                    "response_id": response.get("id"),
                    "connection_id": connection_id,
                    "status": response.get("status")
                }
            )
            
        elif message_type == "response.done":
            # Assistant response completed
            response = message.get("response", {})
            conversation_tracker.log_system_event(
                event="Assistant response completed",
                event_metadata={
                    "response_id": response.get("id"),
                    "connection_id": connection_id,
                    "status": response.get("status"),
                    "usage": response.get("usage", {})
                }
            )
            
        elif message_type == "input_audio_buffer.speech_started":
            # User started speaking
            conversation_tracker.log_system_event(
                event="User speech started",
                event_metadata={
                    "connection_id": connection_id,
                    "audio_start_ms": message.get("audio_start_ms"),
                    "item_id": message.get("item_id")
                }
            )
            
        elif message_type == "input_audio_buffer.speech_stopped":
            # User stopped speaking
            conversation_tracker.log_system_event(
                event="User speech stopped",
                event_metadata={
                    "connection_id": connection_id,
                    "audio_end_ms": message.get("audio_end_ms"),
                    "item_id": message.get("item_id")
                }
            )
            
        elif message_type == "error":
            # Error occurred
            error = message.get("error", {})
            conversation_tracker.log_system_event(
                event=f"Voice session error: {error.get('message', 'Unknown error')}",
                event_metadata={
                    "connection_id": connection_id,
                    "error_type": error.get("type"),
                    "error_code": error.get("code"),
                    "error_message": error.get("message")
                }
            )
    
    def _extract_content_from_item(self, item: Dict[str, Any]) -> str:
        """
        Extract text content from a conversation item
        
        Args:
            item: Conversation item
            
        Returns:
            Text content or description
        """
        content = item.get("content", [])
        if not content:
            return f"[{item.get('type', 'unknown')} item]"
        
        text_parts = []
        for part in content:
            if part.get("type") == "input_text":
                text_parts.append(part.get("text", ""))
            elif part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif part.get("type") == "input_audio":
                text_parts.append("[audio input]")
            elif part.get("type") == "audio":
                text_parts.append("[audio response]")
        
        return " ".join(text_parts) if text_parts else f"[{item.get('type', 'unknown')} content]"
    
    async def send_to_session(self, session_id: str, message: Dict[str, Any]):
        """
        Send message to a specific session's WebSocket
        
        Args:
            session_id: Session ID
            message: Message to send
        """
        connection_id = self.session_connections.get(session_id)
        if connection_id and connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                self.logger.error(f"❌ Error sending message to session {session_id}: {e}")
    
    async def broadcast_to_all(self, message: Dict[str, Any]):
        """
        Broadcast message to all connected WebSockets
        
        Args:
            message: Message to broadcast
        """
        disconnected = []
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                self.logger.error(f"❌ Error broadcasting to {connection_id}: {e}")
                disconnected.append(connection_id)
        
        # Clean up disconnected connections
        for connection_id in disconnected:
            self.disconnect(connection_id)
    
    def get_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about active voice sessions
        
        Returns:
            Dictionary of session information
        """
        sessions = {}
        for session_id, connection_id in self.session_connections.items():
            if connection_id in self.active_connections:
                sessions[session_id] = {
                    "connection_id": connection_id,
                    "connected": True,
                    "conversation_session": conversation_tracker.current_session_id
                }
        
        return sessions
    
    def _get_session_id_for_connection(self, connection_id: str) -> str:
        """
        Helper: Get session ID for a connection ID
        """
        for session_id, conn_id in self.session_connections.items():
            if conn_id == connection_id:
                return session_id
        return f"session_{connection_id}"  # fallback session ID
    
    async def _store_in_azure_thread(self, user_message: str, session_id: str, connection_id: str):
        """
        ADDITIONAL: Store voice conversation in Azure AI Foundry thread
        This is additive - if it fails, existing functionality continues unaffected
        """
        try:
            if not self.voice_executor:
                self.logger.debug("Voice executor not available - skipping Azure thread storage")
                return
            
            if not RequestContext or not new_agent_text_message:
                self.logger.debug("A2A imports not available - skipping Azure thread storage")
                return
            
            # Create a message object
            message = new_agent_text_message(user_message)
            
            # Create request context
            class SimpleRequestContext:
                def __init__(self, task, session_id):
                    self.task = task
                    self.session_id = session_id
                    self.current_task = None
            
            request_context = SimpleRequestContext(message, session_id)
            
            # Process through voice executor (this will store in Azure thread)
            async for response in self.voice_executor.execute(request_context):
                # We don't need to do anything with the response here
                # The execute method will handle storing in Azure thread
                pass
                
            self.logger.debug(f"✅ Voice message stored in Azure thread for session {session_id}")
            
        except Exception as e:
            # CRITICAL: Don't break existing functionality if Azure thread storage fails
            self.logger.error(f"⚠️ Azure thread storage failed (non-critical): {e}")
            # Existing voice functionality continues unaffected

# Global WebSocket handler instance
voice_websocket_handler = VoiceWebSocketHandler()