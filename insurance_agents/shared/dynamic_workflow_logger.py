"""
Dynamic Workflow Logger for Intelligent Claims Orchestrator
Tracks real-time workflow steps and provides API endpoints for frontend consumption
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import asyncio
import threading
import time


class WorkflowStepType(Enum):
    """Types of workflow steps"""
    INITIALIZATION = "initialization"
    AGENT_DISCOVERY = "agent_discovery"
    CLAIM_EXTRACTION = "claim_extraction"
    USER_CONFIRMATION = "user_confirmation"
    COVERAGE_EVALUATION = "coverage_evaluation"
    DOCUMENT_ANALYSIS = "document_analysis"
    INTAKE_PROCESSING = "intake_processing"
    FINAL_DECISION = "final_decision"
    ERROR = "error"


class WorkflowStepStatus(Enum):
    """Status of workflow steps"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DynamicWorkflowLogger:
    """
    Tracks workflow steps in real-time and provides API access
    """
    
    def __init__(self, workflow_logs_dir: str = None):
        if workflow_logs_dir is None:
            # Default to the workflow_logs directory in the project
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            workflow_logs_dir = os.path.join(project_root, "workflow_logs")
        
        self.workflow_logs_dir = workflow_logs_dir
        self.workflow_steps_file = os.path.join(workflow_logs_dir, "current_workflow_steps.json")
        
        # Ensure directory exists
        os.makedirs(workflow_logs_dir, exist_ok=True)
        
        # In-memory workflow tracking
        self.current_workflows: Dict[str, List[Dict]] = {}
        self.lock = threading.Lock()
        
        # File monitoring for auto-reload
        self.last_file_mtime = 0
        self.monitoring_enabled = True
        self.monitoring_thread = None
        
        # Initialize empty file if it doesn't exist, then load existing data
        if not os.path.exists(self.workflow_steps_file):
            self._save_to_file({})
        else:
            # Load existing data on startup
            self.load_from_file()
        
        # Start file monitoring thread
        self.start_file_monitoring()
    
    def start_workflow(self, session_id: str, claim_id: str = None) -> str:
        """Start a new workflow tracking session"""
        with self.lock:
            workflow_id = f"workflow_{session_id}_{int(datetime.now().timestamp())}"
            
            # Initialize workflow with first step
            initial_step = {
                "step_id": str(uuid.uuid4()),
                "workflow_id": workflow_id,
                "session_id": session_id,
                "claim_id": claim_id,
                "step_type": WorkflowStepType.INITIALIZATION.value,
                "title": "🚀 Workflow Initialization",
                "description": f"Starting claims processing workflow{' for ' + claim_id if claim_id else ''}",
                "status": WorkflowStepStatus.COMPLETED.value,
                "timestamp": datetime.now().isoformat(),
                "duration_ms": None,
                "details": {
                    "session_id": session_id,
                    "claim_id": claim_id
                }
            }
            
            self.current_workflows[session_id] = [initial_step]
            self._save_to_file(self.current_workflows)
            
            return workflow_id
    
    def add_step(self, 
                 session_id: str,
                 step_type: WorkflowStepType,
                 title: str,
                 description: str,
                 status: WorkflowStepStatus = WorkflowStepStatus.IN_PROGRESS,
                 details: Dict[str, Any] = None) -> str:
        """Add a new workflow step"""
        
        with self.lock:
            if session_id not in self.current_workflows:
                self.current_workflows[session_id] = []
            
            step_id = str(uuid.uuid4())
            step = {
                "step_id": step_id,
                "session_id": session_id,
                "step_type": step_type.value,
                "title": title,
                "description": description,
                "status": status.value,
                "timestamp": datetime.now().isoformat(),
                "duration_ms": None,
                "details": details or {}
            }
            
            self.current_workflows[session_id].append(step)
            self._save_to_file(self.current_workflows)
            
            return step_id
    
    def update_step_status(self, 
                          session_id: str,
                          step_id: str,
                          status: WorkflowStepStatus,
                          description: str = None,
                          details: Dict[str, Any] = None):
        """Update the status of an existing step"""
        
        with self.lock:
            if session_id in self.current_workflows:
                for step in self.current_workflows[session_id]:
                    if step["step_id"] == step_id:
                        step["status"] = status.value
                        if description:
                            step["description"] = description
                        if details:
                            step["details"].update(details)
                        
                        # Calculate duration if completing
                        if status in [WorkflowStepStatus.COMPLETED, WorkflowStepStatus.FAILED]:
                            start_time = datetime.fromisoformat(step["timestamp"])
                            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                            step["duration_ms"] = duration_ms
                        
                        self._save_to_file(self.current_workflows)
                        break
    
    def get_workflow_steps(self, session_id: str) -> List[Dict]:
        """Get all steps for a specific workflow session or claim ID"""
        with self.lock:
            # First try direct session lookup
            if session_id in self.current_workflows:
                return self.current_workflows[session_id]
            
            # If not found, try to find by claim ID (legacy compatibility)
            for sess_id, steps in self.current_workflows.items():
                for step in steps:
                    if step.get("claim_id") == session_id:
                        return steps
            
            return []
    
    def get_latest_workflows(self, limit: int = 10) -> Dict[str, List[Dict]]:
        """Get the most recent workflow sessions"""
        with self.lock:
            # Sort by most recent activity
            sorted_sessions = sorted(
                self.current_workflows.items(),
                key=lambda x: max([step["timestamp"] for step in x[1]] if x[1] else [""]),
                reverse=True
            )
            return dict(sorted_sessions[:limit])
    
    def clear_workflow(self, session_id: str):
        """Clear workflow steps for a session"""
        with self.lock:
            if session_id in self.current_workflows:
                del self.current_workflows[session_id]
                self._save_to_file(self.current_workflows)
    
    def _save_to_file(self, data: Dict):
        """Save workflow data to file"""
        try:
            with open(self.workflow_steps_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving workflow steps: {e}")
    
    def load_from_file(self) -> Dict:
        """Load workflow data from file"""
        try:
            if os.path.exists(self.workflow_steps_file):
                with open(self.workflow_steps_file, 'r') as f:
                    data = json.load(f)
                    with self.lock:
                        self.current_workflows = data
                        # Update last modification time
                        self.last_file_mtime = os.path.getmtime(self.workflow_steps_file)
                    print(f"📊 Loaded {len(data)} workflow sessions from file")
                    return data
            else:
                # Try to load from legacy workflow_steps.json if current file doesn't exist
                legacy_file = os.path.join(self.workflow_logs_dir, "workflow_steps.json")
                if os.path.exists(legacy_file):
                    print("🔄 Found legacy workflow_steps.json, converting to new format...")
                    self._convert_legacy_format(legacy_file)
                    return self.current_workflows
            return {}
        except Exception as e:
            print(f"Error loading workflow steps: {e}")
            return {}
    
    def _convert_legacy_format(self, legacy_file_path: str):
        """Convert legacy workflow_steps.json format to new session-based format"""
        try:
            with open(legacy_file_path, 'r') as f:
                legacy_data = json.load(f)
            
            converted_workflows = {}
            
            for claim_id, steps in legacy_data.items():
                if isinstance(steps, list) and steps:
                    # Create a session ID for this claim
                    session_id = f"legacy_{claim_id}_{int(datetime.now().timestamp())}"
                    
                    # Convert each step to new format
                    converted_steps = []
                    for step in steps:
                        if isinstance(step, dict):
                            converted_step = {
                                "step_id": step.get("step_id", str(uuid.uuid4())),
                                "workflow_id": f"workflow_{session_id}",
                                "session_id": session_id,
                                "claim_id": step.get("claim_id", claim_id),
                                "step_type": step.get("step_type", "unknown"),
                                "title": step.get("title", "Legacy Step"),
                                "description": step.get("description", "Converted from legacy format"),
                                "status": step.get("status", "completed"),
                                "timestamp": step.get("timestamp", datetime.now().isoformat()),
                                "duration_ms": step.get("duration_ms"),
                                "details": step.get("details", {})
                            }
                            converted_steps.append(converted_step)
                    
                    if converted_steps:
                        converted_workflows[session_id] = converted_steps
            
            # Save converted data
            with self.lock:
                self.current_workflows = converted_workflows
            self._save_to_file(converted_workflows)
            print(f"✅ Converted {len(converted_workflows)} legacy workflow sessions")
            
        except Exception as e:
            print(f"Error converting legacy format: {e}")
    
    def start_file_monitoring(self):
        """Start monitoring the workflow steps file for changes"""
        if self.monitoring_thread is None:
            self.monitoring_thread = threading.Thread(target=self._monitor_file_changes, daemon=True)
            self.monitoring_thread.start()
            print("🔄 Started file monitoring for automatic workflow updates")
    
    def stop_file_monitoring(self):
        """Stop monitoring the workflow steps file"""
        self.monitoring_enabled = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=1)
    
    def _monitor_file_changes(self):
        """Monitor file changes and reload data when file is modified"""
        while self.monitoring_enabled:
            try:
                if os.path.exists(self.workflow_steps_file):
                    current_mtime = os.path.getmtime(self.workflow_steps_file)
                    if current_mtime > self.last_file_mtime:
                        print("📥 Detected file changes, reloading workflow data...")
                        self.load_from_file()
                time.sleep(2)  # Check every 2 seconds
            except Exception as e:
                print(f"Error monitoring file: {e}")
                time.sleep(5)  # Wait longer on error

    # Legacy compatibility methods for workflow_logger.py API
    def start_claim_processing(self, claim_id: str) -> None:
        """Legacy compatibility: start claim processing"""
        session_id = f"claim_{claim_id}_{int(datetime.now().timestamp())}"
        self.start_workflow(session_id, claim_id)
        return session_id
    
    def log_agent_selection(self, claim_id: str, agent_name: str, reasoning: str = None):
        """Legacy compatibility: log agent selection"""
        session_id = self._find_session_for_claim(claim_id)
        if session_id:
            return self.add_step(
                session_id=session_id,
                step_type=WorkflowStepType.AGENT_DISCOVERY,
                title=f"🤖 Agent Selected: {agent_name}",
                description=reasoning or f"Selected {agent_name} for processing",
                status=WorkflowStepStatus.COMPLETED,
                details={"agent_name": agent_name, "reasoning": reasoning}
            )
    
    def log_task_dispatch(self, claim_id: str, agent_name: str, task_description: str):
        """Legacy compatibility: log task dispatch"""
        session_id = self._find_session_for_claim(claim_id)
        if session_id:
            return self.add_step(
                session_id=session_id,
                step_type=WorkflowStepType.INTAKE_PROCESSING,
                title=f"📤 Task Dispatched to {agent_name}",
                description=task_description,
                status=WorkflowStepStatus.IN_PROGRESS,
                details={"agent_name": agent_name, "task": task_description}
            )
    
    def log_agent_response(self, claim_id: str, agent_name: str, step_id: str, response_data: dict, status: str = "completed"):
        """Legacy compatibility: log agent response"""
        session_id = self._find_session_for_claim(claim_id)
        if session_id:
            workflow_status = WorkflowStepStatus.COMPLETED if status == "completed" else WorkflowStepStatus.FAILED
            self.update_step_status(
                session_id=session_id,
                step_id=step_id,
                status=workflow_status,
                description=f"Response from {agent_name}",
                details=response_data
            )
    
    def log_completion(self, claim_id: str, final_result: dict):
        """Legacy compatibility: log workflow completion"""
        session_id = self._find_session_for_claim(claim_id)
        if session_id:
            return self.add_step(
                session_id=session_id,
                step_type=WorkflowStepType.FINAL_DECISION,
                title="✅ Workflow Completed",
                description="Claims processing workflow completed successfully",
                status=WorkflowStepStatus.COMPLETED,
                details=final_result
            )
    
    def _find_session_for_claim(self, claim_id: str) -> Optional[str]:
        """Find the session ID for a given claim ID"""
        with self.lock:
            for session_id, steps in self.current_workflows.items():
                for step in steps:
                    if step.get("claim_id") == claim_id:
                        return session_id
            # If not found, create a new session
            return f"claim_{claim_id}_{int(datetime.now().timestamp())}"
    
    # Additional legacy compatibility methods for dashboard
    def _load_from_file(self):
        """Legacy compatibility: load from file"""
        return self.load_from_file()
    
    def get_all_recent_steps(self, limit: int = 20) -> List[Dict]:
        """Legacy compatibility: get all recent steps across all workflows"""
        all_steps = []
        with self.lock:
            for session_id, steps in self.current_workflows.items():
                for step in steps:
                    step_copy = step.copy()
                    step_copy["session_id"] = session_id
                    all_steps.append(step_copy)
        
        # Sort by timestamp and return most recent
        all_steps.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_steps[:limit]
    
    @property
    def storage_file(self):
        """Legacy compatibility: storage file path"""
        from pathlib import Path
        return Path(self.workflow_steps_file)


# Global workflow logger instance
workflow_logger = DynamicWorkflowLogger()
