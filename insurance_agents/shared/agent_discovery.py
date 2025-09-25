"""
Enhanced Agent Discovery Module
Adds detailed agent discovery, capability matching, and routing decisions
Includes dynamic discovery with background polling and on-demand checking
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import aiohttp
import json


class AgentDiscoveryService:
    """
    Enhanced agent discovery with detailed logging and intelligent routing
    Supports both background polling and on-demand discovery
    """
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.discovered_agents = {}
        self.last_discovery = None
        self._background_task = None
        self._is_running = False
        
        # Known agent endpoints (communication_agent hidden by default)
        self.default_agent_endpoints = {
            "intake_clarifier": "http://localhost:8002",
            "document_intelligence": "http://localhost:8003", 
            "coverage_rules_engine": "http://localhost:8004"
        }
        
        # All possible agents (including communication_agent)
        self.all_agent_endpoints = {
            "intake_clarifier": "http://localhost:8002",
            "document_intelligence": "http://localhost:8003", 
            "coverage_rules_engine": "http://localhost:8004",
            "communication_agent": "http://localhost:8005"
        }
        
        # Currently active endpoints (can be modified via UI)
        self.active_agent_endpoints = self.default_agent_endpoints.copy()
    
    def start_background_discovery(self, interval_minutes: int = 2):
        """Start background agent discovery polling"""
        if not self._is_running:
            self._is_running = True
            self._background_task = asyncio.create_task(self._background_discovery_loop(interval_minutes))
            self.logger.info(f"🔄 Started background agent discovery (every {interval_minutes} minutes)")
    
    def stop_background_discovery(self):
        """Stop background agent discovery polling"""
        self._is_running = False
        if self._background_task:
            self._background_task.cancel()
            self.logger.info("🛑 Stopped background agent discovery")
    
    async def _background_discovery_loop(self, interval_minutes: int):
        """Background discovery loop that runs every X minutes"""
        while self._is_running:
            try:
                await asyncio.sleep(interval_minutes * 60)  # Convert to seconds
                if self._is_running:
                    self.logger.info("🔄 Background agent discovery check...")
                    await self.discover_all_agents(silent=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"❌ Background discovery error: {e}")
    
    async def discover_specific_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        On-demand discovery for a specific agent (e.g., communication_agent before email step)
        """
        if agent_id not in self.all_agent_endpoints:
            self.logger.warning(f"⚠️ Unknown agent ID: {agent_id}")
            return None
        
        base_url = self.all_agent_endpoints[agent_id]
        self.logger.info(f"🔍 ON-DEMAND DISCOVERY: Checking {agent_id} at {base_url}")
        
        try:
            agent_info = await self._discover_single_agent(agent_id, base_url)
            if agent_info:
                # Update the discovered agents cache
                self.discovered_agents[agent_id] = agent_info
                self.logger.info(f"✅ {agent_id}: NOW ONLINE with {len(agent_info.get('skills', []))} skills")
                return agent_info
            else:
                self.logger.info(f"❌ {agent_id}: Still offline")
                # Remove from cache if it was there
                self.discovered_agents.pop(agent_id, None)
                return None
        except Exception as e:
            self.logger.error(f"❌ On-demand discovery failed for {agent_id}: {e}")
            return None
    
    def add_agent_to_registry(self, agent_id: str):
        """Add an agent to the active registry (e.g., via UI)"""
        if agent_id in self.all_agent_endpoints:
            self.active_agent_endpoints[agent_id] = self.all_agent_endpoints[agent_id]
            self.logger.info(f"➕ Added {agent_id} to active agent registry")
        else:
            self.logger.warning(f"⚠️ Cannot add unknown agent: {agent_id}")
    
    def remove_agent_from_registry(self, agent_id: str):
        """Remove an agent from the active registry"""
        if agent_id in self.active_agent_endpoints:
            del self.active_agent_endpoints[agent_id]
            self.discovered_agents.pop(agent_id, None)
            self.logger.info(f"➖ Removed {agent_id} from active agent registry")
    
    async def discover_all_agents(self, silent: bool = False) -> Dict[str, Any]:
        """
        Discover all available agents and their capabilities
        Uses active_agent_endpoints (not communication_agent by default)
        """
        if not silent:
            self.logger.info("🔍 AGENT DISCOVERY: Starting agent discovery process...")
        
        discovered = {}
        
        for agent_id, base_url in self.active_agent_endpoints.items():
            if not silent:
                self.logger.info(f"   🤖 Discovering {agent_id} at {base_url}")
            
            try:
                agent_info = await self._discover_single_agent(agent_id, base_url)
                if agent_info:
                    discovered[agent_id] = agent_info
                    if not silent:
                        self.logger.info(f"   ✅ {agent_id}: ONLINE with {len(agent_info.get('skills', []))} skills")
                        
                        # Log capabilities
                        for skill in agent_info.get('skills', []):
                            skill_name = skill.get('name', 'Unknown')
                            self.logger.info(f"      • Skill: {skill_name}")
                else:
                    if not silent:
                        self.logger.warning(f"   ❌ {agent_id}: OFFLINE or no agent card")
                    # Remove from discovered agents if it went offline
                    self.discovered_agents.pop(agent_id, None)
                    
            except Exception as e:
                if not silent:
                    self.logger.error(f"   ❌ {agent_id}: Discovery failed - {str(e)}")
        
        self.discovered_agents = discovered
        self.last_discovery = datetime.now()
        
        if not silent:
            self.logger.info(f"🎯 DISCOVERY COMPLETE: Found {len(discovered)} agents online")
        
        return discovered
    
    async def _discover_single_agent(self, agent_id: str, base_url: str) -> Optional[Dict[str, Any]]:
        """Discover a single agent's capabilities"""
        
        try:
            async with aiohttp.ClientSession() as session:
                # Try agent card endpoint
                agent_card_url = f"{base_url}/.well-known/agent.json"
                
                async with session.get(agent_card_url, timeout=5) as response:
                    if response.status == 200:
                        agent_card = await response.json()
                        
                        return {
                            "agent_id": agent_id,
                            "name": agent_card.get("name", "Unknown Agent"),
                            "base_url": base_url,
                            "skills": agent_card.get("skills", []),
                            "capabilities": agent_card.get("capabilities", {}),
                            "description": agent_card.get("description", ""),
                            "status": "online",
                            "discovered_at": datetime.now().isoformat()
                        }
        
        except Exception as e:
            self.logger.debug(f"Failed to discover {agent_id}: {str(e)}")
            
        return None
    
    def select_agent_for_task(self, task_description: str, task_type: str) -> Optional[Dict[str, Any]]:
        """
        Intelligently select the best agent for a given task
        """
        self.logger.info(f"🎯 AGENT SELECTION: Selecting agent for task type '{task_type}'")
        self.logger.info(f"   📋 Task description: {task_description[:100]}...")
        
        if not self.discovered_agents:
            self.logger.warning("⚠️ No agents discovered yet - run discovery first")
            return None
        
        # Task-to-agent mapping logic
        task_mappings = {
            "intake_validation": ["intake_clarifier"],
            "claim_validation": ["intake_clarifier"],
            "fraud_detection": ["intake_clarifier"],
            "document_analysis": ["document_intelligence"],
            "document_processing": ["document_intelligence"], 
            "text_extraction": ["document_intelligence"],
            "coverage_evaluation": ["coverage_rules_engine"],
            "rules_evaluation": ["coverage_rules_engine"],
            "policy_analysis": ["coverage_rules_engine"]
        }
        
        # Find matching agents
        candidate_agents = []
        
        # Direct mapping
        if task_type in task_mappings:
            for agent_id in task_mappings[task_type]:
                if agent_id in self.discovered_agents:
                    candidate_agents.append(self.discovered_agents[agent_id])
                    self.logger.info(f"   ✅ Direct match: {agent_id} handles {task_type}")
        
        # Skill-based matching
        task_keywords = task_description.lower().split()
        for agent_id, agent_info in self.discovered_agents.items():
            for skill in agent_info.get("skills", []):
                skill_text = (skill.get("name", "") + " " + skill.get("description", "")).lower()
                
                # Check if task keywords match skill
                matches = sum(1 for keyword in task_keywords if keyword in skill_text)
                if matches > 0:
                    if agent_info not in candidate_agents:
                        candidate_agents.append(agent_info)
                        self.logger.info(f"   🎯 Skill match: {agent_id} - '{skill.get('name')}' matches task")
        
        if not candidate_agents:
            self.logger.warning(f"⚠️ No suitable agents found for task type: {task_type}")
            return None
        
        # Select best agent (for now, just take the first match)
        selected_agent = candidate_agents[0]
        
        self.logger.info(f"🎯 SELECTION RESULT: Chose {selected_agent['agent_id']} - {selected_agent['name']}")
        self.logger.info(f"   📊 Reason: Best match for {task_type}")
        self.logger.info(f"   🌐 Will send to: {selected_agent['base_url']}")
        
        return selected_agent
    
    async def send_task_to_agent(self, agent_info: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a task to a specific agent using A2A protocol
        """
        agent_id = agent_info["agent_id"]
        base_url = agent_info["base_url"]
        
        self.logger.info(f"📤 TASK DISPATCH: Sending task to {agent_id}")
        self.logger.info(f"   🎯 Agent: {agent_info['name']}")
        self.logger.info(f"   📋 Task: {task.get('description', 'No description')}")
        
        try:
            # Create A2A message
            a2a_payload = {
                "jsonrpc": "2.0",
                "id": f"task-{agent_id}-{datetime.now().strftime('%H%M%S')}",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"msg-{agent_id}-{datetime.now().strftime('%H%M%S')}",
                        "role": "user",
                        "parts": [
                            {
                                "kind": "text",
                                "text": task.get("message", "Process this task")
                            }
                        ]
                    }
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    base_url,
                    json=a2a_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                ) as response:
                    
                    response_text = await response.text()
                    
                    if response.status < 400:
                        self.logger.info(f"✅ TASK SUCCESS: {agent_id} processed task successfully")
                        return {
                            "status": "success",
                            "agent": agent_id,
                            "response": response_text,
                            "response_code": response.status
                        }
                    else:
                        self.logger.error(f"❌ TASK FAILED: {agent_id} returned {response.status}")
                        return {
                            "status": "failed",
                            "agent": agent_id,
                            "error": response_text,
                            "response_code": response.status
                        }
        
        except Exception as e:
            self.logger.error(f"❌ TASK ERROR: Failed to send task to {agent_id}: {str(e)}")
            return {
                "status": "error",
                "agent": agent_id,
                "error": str(e)
            }
    
    def get_discovery_summary(self) -> str:
        """Get a summary of discovered agents"""
        if not self.discovered_agents:
            return "No agents discovered yet"
        
        summary = f"Discovered {len(self.discovered_agents)} agents:\n"
        for agent_id, agent_info in self.discovered_agents.items():
            skills_count = len(agent_info.get("skills", []))
            summary += f"• {agent_info['name']} ({agent_id}): {skills_count} skills\n"
        
        return summary
