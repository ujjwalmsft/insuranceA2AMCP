"""
Direct Cosmos DB Client for Claims Processing
Provides direct Cosmos DB operations without MCP layer for writing operations
and supporting the new claim processing workflow.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class TerminalLogger:
    """Enhanced terminal logging for Cosmos operations"""
    
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m'
    }
    
    @classmethod
    def log(cls, level: str, component: str, message: str):
        """Log with colors and emojis"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        emoji_map = {
            'INFO': '📋',
            'SUCCESS': '✅', 
            'ERROR': '❌',
            'WARNING': '⚠️',
            'DEBUG': '🔍'
        }
        
        color = {
            'INFO': cls.COLORS['blue'],
            'SUCCESS': cls.COLORS['green'],
            'ERROR': cls.COLORS['red'], 
            'WARNING': cls.COLORS['yellow'],
            'DEBUG': cls.COLORS['magenta']
        }.get(level, cls.COLORS['reset'])
        
        emoji = emoji_map.get(level, '📋')
        print(f"{color}{emoji} [{timestamp}] {component}: {message}{cls.COLORS['reset']}")

class CosmosDBClient:
    """
    Direct Cosmos DB Client for Claims Processing
    Handles reading and writing operations for the new claim workflow
    """
    
    def __init__(self):
        self.logger = TerminalLogger()
        
        # Cosmos DB configuration
        self.cosmos_endpoint = os.getenv('COSMOS_ENDPOINT', os.getenv('COSMOS_URI'))
        self.cosmos_key = os.getenv('COSMOS_KEY')
        self.database_name = os.getenv('COSMOS_DATABASE', 'insurance_claims')
        
        self.client = None
        self.database = None
        self._initialized = False
        
        # Container configurations
        self.containers_config = {
            'claim_details': {
                'partition_key': '/claimId',
                'description': 'Main claims container with claim information and document URLs'
            },
            'extracted_patient_data': {
                'partition_key': '/claimId',
                'description': 'Extracted patient data from Azure Document Intelligence'
            },
            'workflow_logs': {
                'partition_key': '/claimId',
                'description': 'Claims processing workflow logs'
            }
        }
    
    async def initialize(self) -> bool:
        """Initialize Cosmos DB connection and ensure containers exist"""
        try:
            self.logger.log("INFO", "COSMOS_CLIENT", "🚀 Initializing Cosmos DB connection...")
            
            # Validate environment variables
            if not self.cosmos_endpoint:
                self.logger.log("ERROR", "COSMOS_CLIENT", "COSMOS_ENDPOINT/COSMOS_URI environment variable not set")
                return False
                
            if not self.cosmos_key:
                self.logger.log("ERROR", "COSMOS_CLIENT", "COSMOS_KEY environment variable not set")
                return False
            
            self.logger.log("INFO", "COSMOS_CLIENT", f"Endpoint: {self.cosmos_endpoint}")
            self.logger.log("INFO", "COSMOS_CLIENT", f"Database: {self.database_name}")
            
            # Initialize Cosmos client
            self.client = CosmosClient(self.cosmos_endpoint, self.cosmos_key)
            
            # Get or create database
            try:
                self.database = self.client.create_database_if_not_exists(id=self.database_name)
                self.logger.log("SUCCESS", "COSMOS_CLIENT", f"Connected to database: {self.database_name}")
            except exceptions.CosmosHttpResponseError as e:
                self.logger.log("ERROR", "COSMOS_CLIENT", f"Database connection failed: {e}")
                return False
            
            # Ensure required containers exist
            await self._ensure_containers_exist()
            
            self._initialized = True
            self.logger.log("SUCCESS", "COSMOS_CLIENT", "✅ Cosmos DB client initialized successfully")
            return True
            
        except Exception as e:
            self.logger.log("ERROR", "COSMOS_CLIENT", f"Failed to initialize: {str(e)}")
            return False
    
    async def _ensure_containers_exist(self):
        """Ensure all required containers exist"""
        for container_name, config in self.containers_config.items():
            try:
                container = self.database.create_container_if_not_exists(
                    id=container_name,
                    partition_key=PartitionKey(path=config['partition_key']),
                    offer_throughput=400  # Basic throughput
                )
                self.logger.log("SUCCESS", "COSMOS_CLIENT", 
                               f"Container ready: {container_name} - {config['description']}")
            except Exception as e:
                self.logger.log("ERROR", "COSMOS_CLIENT", 
                               f"Failed to create container {container_name}: {str(e)}")
                raise
    
    async def get_claim_by_id(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """
        Get claim details by claim ID from claim_details container
        
        Args:
            claim_id: The claim ID to retrieve
            
        Returns:
            Claim document or None if not found
        """
        try:
            self.logger.log("INFO", "COSMOS_READ", f"🔍 Retrieving claim: {claim_id}")
            
            if not self._initialized:
                raise Exception("Cosmos client not initialized")
            
            container = self.database.get_container_client('claim_details')
            
            # Query for the claim
            query = "SELECT * FROM c WHERE c.claimId = @claimId"
            parameters = [{"name": "@claimId", "value": claim_id}]
            
            items = list(container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            
            if items:
                claim = items[0]
                self.logger.log("SUCCESS", "COSMOS_READ", 
                               f"✅ Found claim: {claim_id} - Status: {claim.get('status')}")
                return claim
            else:
                self.logger.log("WARNING", "COSMOS_READ", f"❌ Claim not found: {claim_id}")
                return None
                
        except Exception as e:
            self.logger.log("ERROR", "COSMOS_READ", f"Failed to get claim {claim_id}: {str(e)}")
            return None
    
    async def update_claim_status(self, claim_id: str, new_status: str, reason: str = None) -> bool:
        """
        Update claim status in claim_details container
        
        Args:
            claim_id: The claim ID to update
            new_status: New status value
            reason: Optional reason for status change
            
        Returns:
            Success boolean
        """
        try:
            self.logger.log("INFO", "COSMOS_WRITE", 
                           f"📝 Updating claim {claim_id} status: {new_status}")
            
            if not self._initialized:
                raise Exception("Cosmos client not initialized")
            
            # Get current claim
            claim = await self.get_claim_by_id(claim_id)
            if not claim:
                self.logger.log("ERROR", "COSMOS_WRITE", f"Cannot update - claim not found: {claim_id}")
                return False
            
            # Update fields
            old_status = claim.get('status', 'unknown')
            claim['status'] = new_status
            claim['lastUpdatedAt'] = datetime.now(timezone.utc).isoformat()
            
            if reason:
                if 'statusHistory' not in claim:
                    claim['statusHistory'] = []
                claim['statusHistory'].append({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'oldStatus': old_status,
                    'newStatus': new_status,
                    'reason': reason
                })
            
            # Write back to Cosmos
            container = self.database.get_container_client('claim_details')
            container.upsert_item(claim)
            
            self.logger.log("SUCCESS", "COSMOS_WRITE", 
                           f"✅ Updated claim {claim_id}: {old_status} → {new_status}")
            return True
            
        except Exception as e:
            self.logger.log("ERROR", "COSMOS_WRITE", 
                           f"Failed to update claim {claim_id} status: {str(e)}")
            return False
    
    async def get_extracted_data(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """
        Get extracted patient data by claim ID
        
        Args:
            claim_id: The claim ID to retrieve extracted data for
            
        Returns:
            Extracted data document or None if not found
        """
        try:
            self.logger.log("INFO", "COSMOS_READ", f"🔍 Retrieving extracted data: {claim_id}")
            
            if not self._initialized:
                raise Exception("Cosmos client not initialized")
            
            container = self.database.get_container_client('extracted_patient_data')
            
            try:
                item = container.read_item(item=claim_id, partition_key=claim_id)
                self.logger.log("SUCCESS", "COSMOS_READ", 
                               f"✅ Found extracted data for claim: {claim_id}")
                return item
            except exceptions.CosmosResourceNotFoundError:
                self.logger.log("INFO", "COSMOS_READ", 
                               f"📋 No extracted data found for claim: {claim_id}")
                return None
                
        except Exception as e:
            self.logger.log("ERROR", "COSMOS_READ", 
                           f"Failed to get extracted data for {claim_id}: {str(e)}")
            return None
    
    async def save_extracted_data(self, claim_id: str, extracted_data: Dict[str, Any]) -> bool:
        """
        Save extracted patient data to extracted_patient_data container
        
        Args:
            claim_id: The claim ID
            extracted_data: The structured extracted data
            
        Returns:
            Success boolean
        """
        try:
            self.logger.log("INFO", "COSMOS_WRITE", 
                           f"💾 Saving extracted data for claim: {claim_id}")
            
            if not self._initialized:
                raise Exception("Cosmos client not initialized")
            
            # Prepare document structure
            document = {
                'id': claim_id,
                'claimId': claim_id,
                'extractedAt': datetime.now(timezone.utc).isoformat(),
                'extractionSource': 'Azure Document Intelligence',
                **extracted_data  # Include all extracted data
            }
            
            container = self.database.get_container_client('extracted_patient_data')
            container.upsert_item(document)
            
            self.logger.log("SUCCESS", "COSMOS_WRITE", 
                           f"✅ Saved extracted data for claim: {claim_id}")
            return True
            
        except Exception as e:
            self.logger.log("ERROR", "COSMOS_WRITE", 
                           f"Failed to save extracted data for {claim_id}: {str(e)}")
            return False
    
    async def log_workflow_step(self, claim_id: str, step_name: str, agent_name: str, 
                               status: str, details: Dict[str, Any] = None) -> bool:
        """
        Log workflow step for debugging and tracking
        
        Args:
            claim_id: The claim ID
            step_name: Name of the workflow step
            agent_name: Agent that performed the step
            status: Step status (success/error/pending)
            details: Additional step details
            
        Returns:
            Success boolean
        """
        try:
            if not self._initialized:
                return False
            
            log_entry = {
                'id': f"{claim_id}_{step_name}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                'claimId': claim_id,
                'stepName': step_name,
                'agentName': agent_name,
                'status': status,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'details': details or {}
            }
            
            container = self.database.get_container_client('workflow_logs')
            container.create_item(log_entry)
            
            self.logger.log("SUCCESS", "WORKFLOW_LOG", 
                           f"📋 Logged step: {step_name} for claim {claim_id} - {status}")
            return True
            
        except Exception as e:
            self.logger.log("ERROR", "WORKFLOW_LOG", 
                           f"Failed to log workflow step: {str(e)}")
            return False
    
    async def query_container(self, container_name: str, query: str, parameters: List[Dict] = None) -> List[Dict[str, Any]]:
        """
        Execute a SQL query on a specific container
        
        Args:
            container_name: Name of the container to query
            query: SQL query string
            parameters: Optional query parameters
            
        Returns:
            List of matching documents
        """
        try:
            self.logger.log("INFO", "COSMOS_QUERY", f"🔍 Querying {container_name}: {query[:100]}...")
            
            if not self._initialized:
                raise Exception("Cosmos client not initialized")
            
            container = self.database.get_container_client(container_name)
            
            items = list(container.query_items(
                query=query,
                parameters=parameters or [],
                enable_cross_partition_query=True
            ))
            
            self.logger.log("SUCCESS", "COSMOS_QUERY", 
                           f"✅ Query returned {len(items)} items from {container_name}")
            return items
            
        except Exception as e:
            self.logger.log("ERROR", "COSMOS_QUERY", 
                           f"Failed to query {container_name}: {str(e)}")
            return []
    
    async def get_all_claims(self) -> List[Dict[str, Any]]:
        """Get all claims from the claim_details container"""
        return await self.query_container('claim_details', 'SELECT * FROM c')
    
    async def search_claims(self, search_term: str = None, status: str = None) -> List[Dict[str, Any]]:
        """
        Search claims with optional filters
        
        Args:
            search_term: Optional text to search in claim fields
            status: Optional status filter
            
        Returns:
            List of matching claims
        """
        query = "SELECT * FROM c"
        parameters = []
        conditions = []
        
        if status:
            conditions.append("c.status = @status")
            parameters.append({"name": "@status", "value": status})
        
        if search_term:
            conditions.append("(CONTAINS(LOWER(c.claimId), LOWER(@search)) OR CONTAINS(LOWER(c.patientName), LOWER(@search)) OR CONTAINS(LOWER(c.diagnosis), LOWER(@search)))")
            parameters.append({"name": "@search", "value": search_term})
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        return await self.query_container('claim_details', query, parameters)
    
    async def check_connection(self) -> bool:
        """Test Cosmos DB connection"""
        try:
            if not self._initialized:
                return False
            
            # Simple test query
            container = self.database.get_container_client('claim_details')
            list(container.query_items("SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True))
            
            self.logger.log("SUCCESS", "COSMOS_TEST", "✅ Connection test successful")
            return True
            
        except Exception as e:
            self.logger.log("ERROR", "COSMOS_TEST", f"Connection test failed: {str(e)}")
            return False

# Global client instance
_cosmos_client = None

async def get_cosmos_client() -> CosmosDBClient:
    """Get or create global Cosmos DB client instance"""
    global _cosmos_client
    
    if _cosmos_client is None:
        _cosmos_client = CosmosDBClient()
        await _cosmos_client.initialize()
    
    return _cosmos_client

# Convenience functions for easy access
async def get_claim(claim_id: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get claim by ID"""
    client = await get_cosmos_client()
    return await client.get_claim_by_id(claim_id)

async def update_claim_status(claim_id: str, status: str, reason: str = None) -> bool:
    """Convenience function to update claim status"""
    client = await get_cosmos_client()
    return await client.update_claim_status(claim_id, status, reason)

async def save_extracted_data(claim_id: str, data: Dict[str, Any]) -> bool:
    """Convenience function to save extracted data"""
    client = await get_cosmos_client()
    return await client.save_extracted_data(claim_id, data)

async def get_extracted_data(claim_id: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get extracted data"""
    client = await get_cosmos_client()
    return await client.get_extracted_data(claim_id)

async def log_workflow_step(claim_id: str, step: str, agent: str, status: str, details: Dict = None) -> bool:
    """Convenience function to log workflow steps"""
    client = await get_cosmos_client()
    return await client.log_workflow_step(claim_id, step, agent, status, details)

async def query_claims(search_term: str = None, status: str = None) -> List[Dict[str, Any]]:
    """Convenience function to search claims"""
    client = await get_cosmos_client()
    return await client.search_claims(search_term, status)

async def get_all_claims() -> List[Dict[str, Any]]:
    """Convenience function to get all claims"""
    client = await get_cosmos_client()
    return await client.get_all_claims()
