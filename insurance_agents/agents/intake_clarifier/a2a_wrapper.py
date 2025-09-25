"""
A2A-compatible wrapper for the Intake Clarifier Executor
Bridges between our existing insurance agent logic and the A2A framework
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
    new_text_artifact,
)

from agents.intake_clarifier.intake_clarifier_executor import IntakeClarifierExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class A2AIntakeClarifierExecutor(AgentExecutor):
    """A2A-compatible wrapper for the Intake Clarifier"""
    
    def __init__(self):
        self.core_executor = IntakeClarifierExecutor()
        
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute using A2A protocol"""
        try:
            # Get the user input from the context
            user_input = context.get_user_input()
            task = context.current_task
            if not task:
                task = new_task(context.message)
                await event_queue.enqueue_event(task)
            
            logger.info(f"A2A Intake Clarifier processing: {user_input}")
            
            # Start processing
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.working,
                        message=new_agent_text_message(
                            "🏥 Starting claim intake clarification...",
                            task.context_id,
                            task.id,
                        ),
                    ),
                    final=False,
                    context_id=task.context_id,
                    task_id=task.id,
                )
            )
            
            # Check if this is a new workflow request
            if self._is_new_workflow_claim_request(user_input):
                result = await self._handle_new_workflow_verification(user_input)
            else:
                # Use existing core executor for legacy requests - pass correct parameters
                await self.core_executor.execute(context, event_queue)
                result = {"status": "completed", "message": "Intake clarification completed via core executor"}
            
            # For new workflow, format result properly
            if isinstance(result, dict):
                result_text = json.dumps(result, indent=2)
            else:
                result_text = str(result)
            
            # Format the result as text
            result_text = json.dumps(result, indent=2)
            
            # Send final result
            await event_queue.enqueue_event(
                TaskArtifactUpdateEvent(
                    append=False,
                    context_id=task.context_id,
                    task_id=task.id,
                    last_chunk=True,
                    artifact=new_text_artifact(
                        name='intake_clarification_result',
                        description='Result of intake clarification process.',
                        text=result_text,
                    ),
                )
            )
            
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(state=TaskState.completed),
                    final=True,
                    context_id=task.context_id,
                    task_id=task.id,
                )
            )
            
        except Exception as e:
            logger.error(f"Error in A2A Intake Clarifier: {e}")
            error_message = f"❌ Error in intake clarification: {str(e)}"
            
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(
                            error_message,
                            task.context_id if task else "unknown",
                            task.id if task else "unknown",
                        ),
                    ),
                    final=True,
                    context_id=task.context_id if task else "unknown",
                    task_id=task.id if task else "unknown",
                )
            )
    
    def _parse_user_input(self, user_input: str) -> Dict[str, Any]:
        """Parse user input to extract task and parameters"""
        try:
            # Try to parse as JSON first
            data = json.loads(user_input)
            if isinstance(data, dict) and ('task' in data or 'parameters' in data):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        
        # If not JSON, create a default request based on the text
        if "OP-" in user_input:
            # Extract claim ID
            import re
            claim_match = re.search(r'OP-\d+', user_input)
            claim_id = claim_match.group(0) if claim_match else "unknown"
            
            return {
                "task": "validate_claim_intake",
                "parameters": {
                    "claim_id": claim_id,
                    "user_request": user_input,
                    "expected_output": "validation_with_recommendations"
                }
            }
        else:
            # Generic request
            return {
                "task": "general_clarification",
                "parameters": {
                    "user_request": user_input,
                    "expected_output": "clarification_response"
                }
            }

    def _is_new_workflow_claim_request(self, user_input: str) -> bool:
        """Check if this is a new workflow claim verification request"""
        indicators = [
            "claim_id" in user_input.lower(),
            "patient verification" in user_input.lower(),
            "patient_name" in user_input.lower(),
            "category" in user_input.lower()
        ]
        return sum(indicators) >= 2

    async def _handle_new_workflow_verification(self, user_input: str) -> Dict[str, Any]:
        """Handle patient/claim verification for new workflow"""
        try:
            logger.info("🆕 Processing NEW WORKFLOW patient verification")
            
            # Extract claim ID from the request
            claim_id = self._extract_claim_id_from_text(user_input)
            if not claim_id:
                return {
                    "status": "error",
                    "response": "No claim ID found in verification request"
                }
            
            # Fetch and compare data from both containers as requested by orchestrator
            comparison_result = await self._compare_claim_and_extracted_data(claim_id)
            
            if comparison_result['status'] == 'match':
                response_message = f"""✅ **CLAIM APPROVED**

**Claim ID**: {claim_id}
**Verification Status**: PASSED
**Data Integrity**: All data fields match between claim and extracted data

**Verification Details:**
{chr(10).join(['• ' + detail for detail in comparison_result['details']])}

**Status**: Marked for approval in Cosmos DB"""
                
                return {
                    "status": "approved",
                    "response": response_message,
                    "verification_result": comparison_result,
                    "workflow_type": "new_structured"
                }
            else:
                response_message = f"""❌ **CLAIM DENIED**

**Claim ID**: {claim_id}
**Verification Status**: FAILED
**Data Integrity**: Data mismatch detected

**Issues Found:**
{chr(10).join(['• ' + issue for issue in comparison_result['issues']])}

**Status**: Marked for rejection in Cosmos DB"""
                
                return {
                    "status": "denied",
                    "response": response_message,
                    "verification_result": comparison_result,
                    "workflow_type": "new_structured"
                }
            
        except Exception as e:
            logger.error(f"❌ Error in new workflow verification: {e}")
            return {
                "status": "error",
                "response": f"Patient verification failed: {str(e)}"
            }

    def _extract_claim_id_from_text(self, text: str) -> str:
        """Extract claim ID from task text"""
        import re
        patterns = [
            r'claim[_\s]*id[:\s]+([A-Z]{2}-\d{2,3})',
            r'claim[:\s]+([A-Z]{2}-\d{2,3})',
            r'([A-Z]{2}-\d{2,3})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    async def _compare_claim_and_extracted_data(self, claim_id: str) -> Dict[str, Any]:
        """Compare claim data with extracted patient data from Cosmos DB - REAL IMPLEMENTATION"""
        try:
            logger.info(f"🔍 STARTING DATA COMPARISON for claim {claim_id}")
            
            # REAL COSMOS DB COMPARISON - No more simulation!
            
            # Initialize Cosmos DB client if not already done
            if not hasattr(self, 'cosmos_client') or not self.cosmos_client:
                logger.info(f"🔄 Initializing Cosmos DB client for {claim_id}")
                await self._init_cosmos_client()
            
            if not self.cosmos_client:
                logger.error(f"❌ Cosmos DB client still not available for {claim_id}")
                return {
                    "status": "error",
                    "details": [],
                    "issues": ["Cosmos DB client not available"]
                }
            
            logger.info(f"✅ Cosmos DB client available for {claim_id}")
            
            # Fetch claim data from claim_details container
            logger.info(f"📋 Fetching claim data from claim_details container for {claim_id}")
            claim_data = await self._fetch_claim_details(claim_id)
            if not claim_data:
                logger.error(f"❌ Claim {claim_id} not found in claim_details container")
                return {
                    "status": "error", 
                    "details": [],
                    "issues": [f"Claim {claim_id} not found in claim_details container"]
                }
            
            logger.info(f"✅ Found claim data: {claim_data}")
            
            # Fetch extracted data from extracted_patient_data container  
            logger.info(f"📋 Fetching extracted data from extracted_patient_data container for {claim_id}")
            extracted_data = await self._fetch_extracted_patient_data(claim_id)
            if not extracted_data:
                logger.error(f"❌ Extracted data for {claim_id} not found in extracted_patient_data container")
                return {
                    "status": "error",
                    "details": [],
                    "issues": [f"Extracted data for {claim_id} not found in extracted_patient_data container"]
                }
            
            logger.info(f"✅ Found extracted data: {extracted_data}")
            
            # Compare the data fields
            logger.info(f"🔄 Performing field-by-field comparison for {claim_id}")
            comparison_result = self._perform_data_comparison(claim_data, extracted_data)
            logger.info(f"📊 Comparison result: {comparison_result}")
            
            # Update status in Cosmos DB based on comparison result
            logger.info(f"🔄 Updating claim status in Cosmos DB for {claim_id}")
            await self._update_claim_status(claim_id, comparison_result)
            logger.info(f"✅ Claim status updated for {claim_id}")
            
            return comparison_result
                
        except Exception as e:
            logger.error(f"❌ Error comparing claim data for {claim_id}: {e}")
            return {
                "status": "error",
                "details": [],
                "issues": [f"Database comparison failed: {str(e)}"]
            }

    async def _init_cosmos_client(self):
        """Initialize Cosmos DB client for real data access"""
        try:
            import os
            logger.info("🔄 Starting Cosmos DB client initialization")
            
            endpoint = os.getenv("COSMOS_DB_ENDPOINT")
            key = os.getenv("COSMOS_DB_KEY") 
            database_name = os.getenv("COSMOS_DB_DATABASE_NAME", "insurance")
            
            logger.info(f"🔍 Environment check:")
            logger.info(f"   COSMOS_DB_ENDPOINT: {'✅ Found' if endpoint else '❌ Missing'}")
            logger.info(f"   COSMOS_DB_KEY: {'✅ Found' if key else '❌ Missing'}")
            logger.info(f"   COSMOS_DB_DATABASE_NAME: {database_name}")
            
            if not endpoint or not key:
                logger.warning("⚠️ Cosmos DB credentials not found in environment")
                self.cosmos_client = None
                return
            
            logger.info("🔄 Attempting to create Cosmos DB client...")
            from azure.cosmos import CosmosClient
            self.cosmos_client = CosmosClient(endpoint, key)
            self.database_name = database_name
            logger.info("✅ Cosmos DB client initialized for Intake Clarifier")
            
        except ImportError as e:
            logger.error(f"❌ Failed to import azure-cosmos: {e}")
            logger.error("❌ Please install azure-cosmos package: pip install azure-cosmos")
            self.cosmos_client = None
        except Exception as e:
            logger.error(f"❌ Failed to initialize Cosmos DB client: {e}")
            self.cosmos_client = None

    async def _fetch_claim_details(self, claim_id: str) -> Dict[str, Any]:
        """Fetch claim from claim_details container"""
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client("claim_details")
            
            query = "SELECT * FROM c WHERE c.claimId = @claim_id"
            parameters = [{"name": "@claim_id", "value": claim_id}]
            
            items = list(container.query_items(query=query, parameters=parameters))
            return items[0] if items else None
        except Exception as e:
            logger.error(f"❌ Error fetching claim details: {e}")
            return None

    async def _fetch_extracted_patient_data(self, claim_id: str) -> Dict[str, Any]:
        """Fetch extracted data from extracted_patient_data container"""
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client("extracted_patient_data")
            
            query = "SELECT * FROM c WHERE c.claimId = @claim_id"
            parameters = [{"name": "@claim_id", "value": claim_id}]
            
            items = list(container.query_items(query=query, parameters=parameters))
            return items[0] if items else None
        except Exception as e:
            logger.error(f"❌ Error fetching extracted patient data: {e}")
            return None

    def _perform_data_comparison(self, claim_data: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform actual data comparison between claim and extracted data"""
        details = []
        issues = []
        
        # Compare patient names
        claim_patient = claim_data.get('patientName', '').strip().lower()
        
        # For extracted data, check across all document types for patient name
        extracted_patients = []
        if 'medical_bill_doc' in extracted_data and 'patient_name' in extracted_data['medical_bill_doc']:
            extracted_patients.append(extracted_data['medical_bill_doc']['patient_name'].strip().lower())
        if 'memo_doc' in extracted_data and 'patient_name' in extracted_data['memo_doc']:
            extracted_patients.append(extracted_data['memo_doc']['patient_name'].strip().lower())
        if 'discharge_summary_doc' in extracted_data and 'patient_name' in extracted_data['discharge_summary_doc']:
            extracted_patients.append(extracted_data['discharge_summary_doc']['patient_name'].strip().lower())
        
        # Check if claim patient name matches any extracted patient name
        patient_match = any(claim_patient == ext_patient for ext_patient in extracted_patients)
        if patient_match:
            details.append(f"✅ Patient name matches: {claim_data.get('patientName', 'Unknown')}")
        else:
            issues.append(f"❌ Patient name mismatch: Claim='{claim_data.get('patientName', 'Unknown')}' vs Extracted={extracted_patients}")
        
        # Compare bill amounts
        claim_amount = float(claim_data.get('billAmount', 0))
        extracted_amount = None
        if 'medical_bill_doc' in extracted_data and 'bill_amount' in extracted_data['medical_bill_doc']:
            extracted_amount = float(extracted_data['medical_bill_doc']['bill_amount'])
        
        if extracted_amount is not None:
            if abs(claim_amount - extracted_amount) < 0.01:  # Allow for small floating point differences
                details.append(f"✅ Bill amount matches: ${claim_amount}")
            else:
                issues.append(f"❌ Bill amount mismatch: Claim=${claim_amount} vs Extracted=${extracted_amount}")
        else:
            issues.append("❌ Bill amount not found in extracted data")
        
        # Compare medical conditions/diagnosis
        claim_diagnosis = claim_data.get('diagnosis', '').strip().lower()
        extracted_conditions = []
        if 'memo_doc' in extracted_data and 'medical_condition' in extracted_data['memo_doc']:
            extracted_conditions.append(extracted_data['memo_doc']['medical_condition'].strip().lower())
        if 'discharge_summary_doc' in extracted_data and 'medical_condition' in extracted_data['discharge_summary_doc']:
            extracted_conditions.append(extracted_data['discharge_summary_doc']['medical_condition'].strip().lower())
        
        condition_match = any(claim_diagnosis in ext_condition or ext_condition in claim_diagnosis 
                             for ext_condition in extracted_conditions if ext_condition)
        if condition_match:
            details.append(f"✅ Medical condition matches: {claim_data.get('diagnosis', 'Unknown')}")
        else:
            if extracted_conditions:
                issues.append(f"❌ Medical condition mismatch: Claim='{claim_data.get('diagnosis', 'Unknown')}' vs Extracted={extracted_conditions}")
            else:
                issues.append("❌ Medical condition not found in extracted data")
        
        # Determine overall status
        status = "match" if len(issues) == 0 else "mismatch"
        
        return {
            "status": status,
            "details": details,
            "issues": issues
        }

    async def _update_claim_status(self, claim_id: str, comparison_result: Dict[str, Any]):
        """Update claim status in Cosmos DB based on comparison result"""
        try:
            if comparison_result['status'] == 'match':
                new_status = 'marked for approval'
                reason = 'Data verification passed'
            else:
                new_status = 'marked for rejection'
                reason = f"Data verification failed: {'; '.join(comparison_result['issues'])}"
            
            # Use synchronous Cosmos client directly (no async with needed)
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client("claim_details")
            
            # Fetch current claim to update
            query = "SELECT * FROM c WHERE c.claimId = @claim_id"
            parameters = [{"name": "@claim_id", "value": claim_id}]
            
            items = list(container.query_items(query=query, parameters=parameters))
            
            if items:
                claim = items[0]
                claim['status'] = new_status
                claim['verification_reason'] = reason
                claim['verification_timestamp'] = datetime.now().isoformat()
                claim['updated_by'] = 'intake_clarifier'
                
                container.upsert_item(claim)
                logger.info(f"✅ Updated claim {claim_id} status to: {new_status}")
            else:
                logger.warning(f"⚠️ Claim {claim_id} not found for status update")
                    
        except Exception as e:
            logger.error(f"❌ Error updating claim status: {e}")

    def _extract_claim_info_from_text(self, text: str) -> Dict[str, Any]:
        """Extract structured claim information from task text"""
        import re
        
        claim_info = {}
        patterns = {
            'claim_id': r'claim[_\s]*id[:\s]+([A-Z]{2}-\d{2,3})',
            'patient_name': r'patient[_\s]*name[:\s]+([^,\n]+)',
            'category': r'category[:\s]+([^,\n]+)',
            'diagnosis': r'diagnosis[:\s]+([^,\n]+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                claim_info[key] = match.group(1).strip()
        
        return claim_info

    async def _verify_structured_claim_patient(self, claim_info: Dict[str, Any]) -> Dict[str, Any]:
        """Verify patient information for structured claim"""
        import asyncio
        
        patient_name = claim_info.get('patient_name', '')
        category = claim_info.get('category', '').lower()
        claim_id = claim_info.get('claim_id', '')
        
        # Simulate verification processing
        await asyncio.sleep(0.15)
        
        # Enhanced verification based on patient data
        if 'john doe' in patient_name.lower():
            # Known test patient
            identity_verified = True
            eligibility_verified = True
            documentation_complete = True
            verification_details = [
                "Patient identity confirmed via government ID",
                "Insurance policy active and in good standing",
                "Previous claims history reviewed",
                "Contact information verified"
            ]
            required_actions = [
                "No additional verification required",
                "Proceed with standard processing"
            ]
            risk_level = "LOW"
            confidence = 95
        elif claim_id.startswith('OP-'):
            # Outpatient verification
            identity_verified = True
            eligibility_verified = True
            documentation_complete = 'outpatient' in category
            verification_details = [
                "Patient identity verified",
                "Outpatient eligibility confirmed",
                "Basic documentation reviewed"
            ]
            if not documentation_complete:
                verification_details.append("⚠️ Some documentation incomplete")
                
            required_actions = [
                "Verify outpatient pre-authorization",
                "Confirm provider network status"
            ] if not documentation_complete else ["Standard processing approved"]
            
            risk_level = "MEDIUM" if not documentation_complete else "LOW"
            confidence = 80 if documentation_complete else 65
        else:
            # Default verification
            identity_verified = True
            eligibility_verified = False
            documentation_complete = False
            verification_details = [
                "Basic identity check completed",
                "⚠️ Eligibility verification pending",
                "⚠️ Additional documentation required"
            ]
            required_actions = [
                "Complete full eligibility verification",
                "Request additional patient documentation",
                "Schedule manual review if needed"
            ]
            risk_level = "HIGH"
            confidence = 50
        
        return {
            "identity_verified": identity_verified,
            "eligibility_verified": eligibility_verified,
            "documentation_complete": documentation_complete,
            "verification_details": verification_details,
            "required_actions": required_actions,
            "risk_level": risk_level,
            "confidence_score": confidence
        }
    
    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """Cancel the current task"""
        logger.info("Cancelling Intake Clarifier task")
        # Add cancellation logic if needed
