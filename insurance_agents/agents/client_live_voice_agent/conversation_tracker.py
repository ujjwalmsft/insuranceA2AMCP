"""
Shared MockConversationTracker for both FastAPI server and Voice Agent Executor
Consolidates conversation tracking functionality into a single reusable class
"""

class MockConversationTracker:
    """
    Mock conversation tracker that supports both FastAPI server and Voice Agent Executor interfaces
    Provides no-op implementations for all conversation tracking methods
    """
    
    def __init__(self):
        self.current_session_id = None
    
    # FastAPI server interface methods
    def get_conversation_stats(self):
        """Get conversation statistics"""
        return {"total_conversations": 0, "active_sessions": 0}
    
    def get_recent_sessions(self, limit=10):
        """Get recent conversation sessions"""
        return []
    
    def get_session_history(self, session_id):
        """Get conversation history for a specific session"""
        return []
    
    def search_conversations(self, query, limit=10):
        """Search conversation history"""
        return []
    
    # Voice Agent Executor interface methods
    def start_session(self, session_data):
        """Start a new conversation session"""
        self.current_session_id = session_data.get('user_session_id', 'default')
    
    def log_voice_interaction(self, *args, **kwargs): 
        """Log voice interaction (no-op)"""
        pass
    
    def log_agent_response(self, *args, **kwargs): 
        """Log agent response (no-op)"""
        pass
    
    def log_system_event(self, *args, **kwargs): 
        """Log system event (no-op)"""
        pass
    
    def end_session(self, *args, **kwargs): 
        """End conversation session"""
        self.current_session_id = None
    
    def get_conversation_history(self, *args, **kwargs): 
        """Get conversation history (alias for compatibility)"""
        return []
    
    def save_conversation(self, *args, **kwargs): 
        """Save conversation (no-op)"""
        pass

# Create shared instance
conversation_tracker = MockConversationTracker()