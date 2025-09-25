"""
FIXED Coverage Rules Engine Executor - A2A Compatible with LLM Classification
This is the corrected version that works with the A2A framework
"""

import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
from pathlib import Path
# From agents/coverage_rules_engine/file.py -> insurance_agents -> insurance/
project_root = Path(__file__).parent.parent.parent.parent  
env_file = project_root / ".env"
load_dotenv(env_file)
print(f"🔍 Loading .env from: {env_file.absolute()}")
print(f"🔍 .env exists: {env_file.exists()}")

# Also try loading from the azure-cosmos-mcp-server path
mcp_env_path = project_root / "azure-cosmos-mcp-server" / "python" / ".env"
if mcp_env_path.exists():
    load_dotenv(mcp_env_path)

# Azure Cosmos DB imports
from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.utils import new_agent_text_message

from shared.mcp_config import A2A_AGENT_PORTS

class CoverageRulesExecutorFixed(AgentExecutor):
    """
    FIXED Coverage Rules Engine Executor - A2A Compatible
    Simplified version that works correctly with A2A framework
    """
    
    def __init__(self):
        self.agent_name = "coverage_rules_engine"
        self.agent_description = "Evaluates coverage rules and calculates benefits for insurance claims"
        self.port = A2A_AGENT_PORTS["coverage_rules_engine"]
        self.logger = self._setup_logging()
        self.rule_sets = self._initialize_rule_sets()
        
        # Initialize Cosmos DB client
        self._init_cosmos_client()
        
    def _setup_logging(self) -> logging.Logger:
        """Setup colored logging for the agent"""
        logger = logging.getLogger(f"InsuranceAgent.{self.agent_name}")
        
        # Create colored formatter
        formatter = logging.Formatter(
            f"⚖️ [COVERAGE_RULES_FIXED] %(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S"
        )
        
        # Setup console handler
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        
        return logger
    
    def _initialize_rule_sets(self) -> Dict[str, Dict[str, Any]]:
        """Initialize business rule sets according to YOUR VISION"""
        return {
            # YOUR UPDATED SPECIFIC BUSINESS RULES
            "claim_type_limits": {
                "eye": {
                    "max_amount": 500,  # Updated: Eye claims limit $500
                    "keywords": ["eye", "vision", "optic", "retina", "cornea", "lens", "cataract", "glaucoma", "macular", "ocular"],
                    "description": "Eye-related medical conditions"
                },
                "dental": {
                    "max_amount": 1000,  # Updated: Dental claims limit $1000  
                    "keywords": ["dental", "tooth", "teeth", "gum", "oral", "mouth", "periodontal", "cavity", "root canal"],
                    "description": "Dental and oral health conditions"
                },
                "general": {
                    "max_amount": 200000,  # Updated: General claims limit $200,000
                    "keywords": [],  # Everything else falls into general
                    "description": "General medical conditions"
                }
            },
            "document_requirements": {
                "inpatient": {
                    "required_documents": ["discharge_summary_doc", "medical_bill_doc", "memo_doc"],
                    "description": "Inpatient claims require discharge summary, medical bill, and memo"
                },
                "outpatient": {
                    "required_documents": ["medical_bill_doc", "memo_doc"],
                    "description": "Outpatient claims require medical bill and memo"
                }
            },
            "workflow_rules": {
                "approval_flow": "coverage_rules → document_intelligence → intake_clarifier",
                "rejection_flow": "coverage_rules → update_status_to_rejected",
                "containers": {
                    "input": "claim_details",
                    "output": "extracted_patient_details"
                }
            }
        }
    
    def _init_cosmos_client(self):
        """Initialize Cosmos DB client for direct database access"""
        try:
            # Get Cosmos DB configuration from environment (try multiple variable names for compatibility)
            self.cosmos_endpoint = os.getenv("COSMOS_ENDPOINT") or os.getenv("COSMOS_URI") or os.getenv("COSMOS_DB_ENDPOINT")
            self.cosmos_key = os.getenv("COSMOS_KEY") or os.getenv("COSMOS_DB_KEY")
            self.database_name = os.getenv("COSMOS_DATABASE", "insurance")
            self.container_name = os.getenv("COSMOS_CONTAINER", "claim_details")
            
            if not self.cosmos_endpoint or not self.cosmos_key:
                self.logger.warning("⚠️ Cosmos DB credentials not found, direct access disabled")
                self.cosmos_client = None
                return
            
            # Initialize async Cosmos client
            self.cosmos_client = CosmosClient(self.cosmos_endpoint, self.cosmos_key)
            self.logger.info("✅ Cosmos DB client initialized for direct access")
            
            # Disable verbose Azure logging
            logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Cosmos DB client: {e}")
            self.cosmos_client = None
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute a request using the Coverage Rules Engine logic with A2A framework
        FIXED VERSION - Works with correct A2A parameters
        """
        try:
            # Try the intake clarifier approach first
            user_input = context.get_user_input()
            print(f"\n🔍 COVERAGE EXECUTE - User input method: '{user_input}'")
            print(f"🔍 COVERAGE EXECUTE - User input length: {len(user_input) if user_input else 0}")
            
            # Extract message from context (old method)
            message = context.message
            task_text = ""
            
            # Extract text from message parts
            if hasattr(message, 'parts') and message.parts:
                for part in message.parts:
                    if hasattr(part, 'text'):
                        task_text += part.text + " "
            
            task_text = task_text.strip()
            
            # DEBUG: Compare both methods
            print(f"\n🔍 COVERAGE EXECUTE - Old method length: {len(task_text)}")
            print(f"🔍 COVERAGE EXECUTE - Old method text: '{task_text}'")
            
            # Use the working method
            final_task_text = user_input if user_input else task_text
            print(f"🔍 COVERAGE EXECUTE - Using final text: '{final_task_text[:200]}...'")
            
            self.logger.info(f"🔄 A2A Executing task: {final_task_text[:100]}...")
            
            # Process the coverage rules evaluation
            result = await self._process_coverage_rules_task(final_task_text)
            
            # Create and send response message
            response_message = new_agent_text_message(
                text=result.get("response", "Coverage evaluation completed successfully"),
                task_id=getattr(context, 'task_id', None)
            )
            await event_queue.enqueue_event(response_message)
            
            self.logger.info("✅ Coverage rules evaluation completed successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Execution error: {str(e)}")
            
            # Send error message
            error_message = new_agent_text_message(
                text=f"Coverage Rules Engine error: {str(e)}",
                task_id=getattr(context, 'task_id', None)
            )
            await event_queue.enqueue_event(error_message)
    
    async def cancel(self, task_id: str) -> None:
        """
        Cancel a running task - required by A2A AgentExecutor
        """
        self.logger.info(f"🚫 Cancelling task: {task_id}")
        # Implementation for task cancellation if needed
        pass
    
    async def _process_coverage_rules_task(self, task_text: str) -> Dict[str, Any]:
        """Process coverage rules evaluation based on the request text with new workflow support"""
        
        print(f"\n🔍 COVERAGE TASK - Processing task: '{task_text[:100]}...'")
        
        task_lower = task_text.lower()
        
        # Check if this is a new workflow request with claim details
        if self._is_new_workflow_claim_request(task_text):
            print("🔍 COVERAGE TASK - Using NEW WORKFLOW path")
            return await self._handle_new_workflow_claim_evaluation(task_text)
        
        # Legacy processing
        print("🔍 COVERAGE TASK - Using LEGACY path")
        self.logger.info("⚖️ Evaluating coverage rules (legacy mode)...")
        await asyncio.sleep(0.1)  # Simulate processing time
        
        # Extract claim amount if present
        import re
        amount_match = re.search(r'\$(\d+)', task_text)
        claim_amount = float(amount_match.group(1)) if amount_match else 850.0
        
        # Determine claim type
        claim_type = "medical"
        if 'surgical' in task_lower:
            claim_type = "surgical"
        elif 'consultation' in task_lower:
            claim_type = "consultation"
        
        # Apply coverage rules
        coverage_rules = self.rule_sets["coverage_rules"].get(claim_type, self.rule_sets["coverage_rules"]["medical"])
        
        # Calculate coverage
        deductible = coverage_rules.get("deductible", 500)
        max_benefit = coverage_rules.get("max_benefit", 50000)
        
        covered_amount = min(claim_amount - deductible, max_benefit)
        coverage_percentage = (covered_amount / claim_amount) * 100 if claim_amount > 0 else 0
        
        result = {
            "agent": "coverage_rules_engine",
            "task": task_text,
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "evaluation": {
                "claim_type": claim_type,
                "claim_amount": claim_amount,
                "deductible": deductible,
                "max_benefit": max_benefit,
                "covered_amount": max(covered_amount, 0),
                "coverage_percentage": round(coverage_percentage, 2),
                "eligibility": "approved" if covered_amount > 0 else "denied"
            }
        }
        
        if 'evaluate' in task_lower or 'coverage' in task_lower:
            result["evaluation"]["focus"] = "Coverage rules evaluation"
        elif 'calculate' in task_lower or 'benefit' in task_lower:
            result["evaluation"]["focus"] = "Benefit calculation"
        elif 'policy' in task_lower or 'limitation' in task_lower:
            result["evaluation"]["focus"] = "Policy limitations analysis"
        else:
            result["evaluation"]["focus"] = "General coverage evaluation"
        
        result["response"] = json.dumps({
            "status": "success", 
            "message": f"Coverage evaluation completed: {result['evaluation']['focus']}",
            "eligibility": result["evaluation"]["eligibility"],
            "covered_amount": result["evaluation"]["covered_amount"],
            "coverage_percentage": result["evaluation"]["coverage_percentage"],
            "deductible": result["evaluation"]["deductible"]
        }, indent=2)
        
        self.logger.info(f"📊 Coverage: {result['evaluation']['coverage_percentage']}% - ${result['evaluation']['covered_amount']}")
        
        return result

    def _is_new_workflow_claim_request(self, task_text: str) -> bool:
        """Check if this is a new workflow claim evaluation request"""
        # DEBUG: Print to console for immediate visibility
        print(f"\n🔍 COVERAGE DEBUG - Received text: '{task_text[:200]}...'")
        
        # Look for structured claim data patterns
        indicators = [
            "claim_id" in task_text.lower(),
            "patient_name" in task_text.lower(), 
            "bill_amount" in task_text.lower(),
            "diagnosis" in task_text.lower(),
            "category" in task_text.lower()
        ]
        
        indicator_count = sum(indicators)
        print(f"🔍 COVERAGE DEBUG - Found {indicator_count}/5 indicators: {dict(zip(['claim_id', 'patient_name', 'bill_amount', 'diagnosis', 'category'], indicators))}")
        
        is_new_workflow = indicator_count >= 2
        print(f"🔍 COVERAGE DEBUG - New workflow detected: {is_new_workflow}")
        
        return is_new_workflow

    async def _handle_new_workflow_claim_evaluation(self, task_text: str) -> Dict[str, Any]:
        """Handle claim evaluation for new workflow with structured claim data"""
        try:
            print("🔍 COVERAGE - Starting NEW WORKFLOW processing")
            self.logger.info("🆕 Processing NEW WORKFLOW claim evaluation")
            
            # Extract structured claim information
            claim_info = self._extract_claim_info_from_text(task_text)
            print(f"🔍 COVERAGE - Extracted claim info: {claim_info}")
            
            # Perform enhanced coverage evaluation
            evaluation_result = await self._evaluate_structured_claim(claim_info)
            print(f"🔍 COVERAGE - Evaluation result: {evaluation_result}")
            
            response_message = f"""⚖️ **COVERAGE RULES EVALUATION COMPLETE**

**Claim Analysis:**
• **Claim ID**: {claim_info.get('claim_id', 'Unknown')}
• **Category**: {claim_info.get('category', 'Unknown')}
• **Diagnosis**: {claim_info.get('diagnosis', 'Unknown')}
• **Bill Amount**: ${claim_info.get('bill_amount', 0)}

**Business Rules Evaluation:**
• **Claim Type**: {evaluation_result.get('claim_type', 'Unknown').upper()}
• **Maximum Allowed**: ${evaluation_result.get('max_allowed', 0)}
• **Status**: {'✅ APPROVED' if evaluation_result['eligible'] else '❌ REJECTED'}

**Rules Applied:**
{chr(10).join(['• ' + rule for rule in evaluation_result['rules_applied']])}

**Workflow Decision:**
{f"• ❌ REJECTED: {evaluation_result['rejection_reason']}" if not evaluation_result['eligible'] else f"• ✅ APPROVED: Continue to {evaluation_result['next_agent']}"}

**Next Action**: {evaluation_result['workflow_action'].replace('_', ' ').title()}
"""

            return {
                "status": "success",
                "response": response_message,
                "evaluation": evaluation_result,
                "workflow_type": "new_structured"
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error in new workflow evaluation: {e}")
            return {
                "status": "error",
                "response": f"Coverage evaluation failed: {str(e)}"
            }

    def _extract_claim_info_from_text(self, text: str) -> Dict[str, Any]:
        """Extract structured claim information from task text using LLM"""
        try:
            # Use LLM to extract claim information and complete document data
            from openai import AzureOpenAI
            
            client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version="2024-02-15-preview",
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            
            extraction_prompt = f"""
            Extract claim information from the following text. If the text contains a "Complete Document Data" section or "Document 1:" section, extract all attachment URLs and relevant fields from it.
            
            Text: {text}
            
            Look for these patterns:
            - billAttachment: [URL]
            - memoAttachment: [URL]  
            - dischargeAttachment: [URL]
            - Any https:// URLs containing .pdf files
            
            Return a JSON object with the following structure:
            {{
                "claim_id": "extracted claim ID",
                "patient_name": "extracted patient name", 
                "bill_amount": "extracted bill amount (number only)",
                "diagnosis": "extracted diagnosis",
                "category": "extracted category",
                "billAttachment": "URL if found",
                "memoAttachment": "URL if found", 
                "dischargeAttachment": "URL if found"
            }}
            
            Extract URLs from lines like:
            - memoAttachment: https://...
            - billAttachment: https://...
            
            Only include fields that are actually found in the text.
            Return only valid JSON, no explanations.
            """
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a data extraction expert. Extract information exactly as requested and return only valid JSON."},
                    {"role": "user", "content": extraction_prompt}
                ],
                temperature=0,
                max_tokens=1000
            )
            
            extracted_data = response.choices[0].message.content.strip()
            
            # Debug output
            self.logger.info(f"🧠 LLM raw response: '{extracted_data}'")
            
            # Clean up LLM response - remove markdown code blocks if present
            if extracted_data.startswith('```json'):
                extracted_data = extracted_data[7:]  # Remove ```json
            if extracted_data.startswith('```'):
                extracted_data = extracted_data[3:]  # Remove ```
            if extracted_data.endswith('```'):
                extracted_data = extracted_data[:-3]  # Remove trailing ```
            extracted_data = extracted_data.strip()
            
            # Parse the JSON response
            import json
            claim_info = json.loads(extracted_data)
            
            # Log what was extracted
            self.logger.info(f"🧠 LLM extracted claim info with {len(claim_info)} fields")
            
            # Check for attachment URLs at top level
            attachment_types = ['billAttachment', 'memoAttachment', 'dischargeAttachment']
            attachment_count = sum(1 for att_type in attachment_types 
                                 if att_type in claim_info and claim_info[att_type])
            
            if attachment_count > 0:
                self.logger.info(f"📎 LLM found {attachment_count} attachments in extracted data")
                for att_type in attachment_types:
                    if att_type in claim_info and claim_info[att_type]:
                        self.logger.info(f"🔗 {att_type}: {claim_info[att_type]}")
            
            return claim_info
            
        except Exception as e:
            self.logger.error(f"❌ Error in LLM extraction: {e}")
            
            # Fallback to basic regex extraction
            import re
            claim_info = {}
            
            patterns = {
                'claim_id': r'claim[_\s]*id[:\s]+([A-Z]{2}-\d{2,3})',
                'patient_name': r'patient[_\s]*name[:\s]+([^,\n]+)',
                'bill_amount': r'bill[_\s]*amount[:\s]+\$?(\d+(?:\.\d{2})?)',
                'diagnosis': r'diagnosis[:\s]+([^,\n]+)',
                'category': r'category[:\s]+([^,\n]+)'
            }
            
            # Extract attachment URLs directly
            attachment_patterns = {
                'billAttachment': r'billAttachment[:\s]+(https://[^\s\n]+)',
                'memoAttachment': r'memoAttachment[:\s]+(https://[^\s\n]+)',
                'dischargeAttachment': r'dischargeAttachment[:\s]+(https://[^\s\n]+)'
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    claim_info[key] = match.group(1).strip()
            
            # Extract attachment URLs
            for att_type, pattern in attachment_patterns.items():
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    claim_info[att_type] = match.group(1).strip()
                    self.logger.info(f"📎 Regex found {att_type}: {claim_info[att_type]}")
            
            self.logger.warning(f"⚠️ Used fallback regex extraction due to LLM error")
            return claim_info

    async def _evaluate_structured_claim(self, claim_info: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate coverage based on YOUR SPECIFIC BUSINESS RULES"""
        self.logger.info(f"⚖️ Evaluating claim with YOUR business rules: {claim_info}")
        
        # Get claim details
        category = claim_info.get('category', '').lower()
        bill_amount = float(claim_info.get('bill_amount', 0))
        diagnosis = claim_info.get('diagnosis', '').lower()
        claim_id = claim_info.get('claim_id', 'Unknown')
        
        rules_applied = []
        rejection_reason = None
        
        # PRE-VALIDATION CHECKS - New Enhanced Logic
        self.logger.info(f"🔍 Starting pre-validation checks for claim {claim_id}")
        
        # STEP 0.1: Check if claim is already approved
        claim_status_check = await self._check_claim_status(claim_id)
        if not claim_status_check["can_process"]:
            self.logger.info(f"⏹️ Pre-validation failed: {claim_status_check['reason']}")
            return {
                "eligible": False,
                "claim_type": "pre_validation_failed",
                "max_allowed": 0,
                "bill_amount": bill_amount,
                "amount_within_limit": False,
                "required_documents": [],
                "rules_applied": [f"❌ PRE-VALIDATION FAILED: {claim_status_check['reason']}"],
                "rejection_reason": claim_status_check['reason'],
                "workflow_action": "stop_processing",
                "next_agent": "none",
                "status": "denied_pre_validation"
            }
        
        # STEP 0.2: Check if documents are already processed
        doc_processing_check = await self._check_document_processing_status(claim_id)
        if not doc_processing_check["can_process"]:
            self.logger.info(f"⏹️ Pre-validation failed: {doc_processing_check['reason']}")
            return {
                "eligible": False,
                "claim_type": "pre_validation_failed",
                "max_allowed": 0,
                "bill_amount": bill_amount,
                "amount_within_limit": False,
                "required_documents": [],
                "rules_applied": [f"❌ PRE-VALIDATION FAILED: {doc_processing_check['reason']}"],
                "rejection_reason": doc_processing_check['reason'],
                "workflow_action": "stop_processing",
                "next_agent": "none",
                "status": "denied_pre_validation"
            }
        
        # Pre-validation passed - continue with normal rules
        rules_applied.append("✅ Pre-validation checks passed")
        self.logger.info(f"✅ Pre-validation checks passed for claim {claim_id}")
        
        # STEP 0: Check if orchestrator provided complete document data already
        # The orchestrator now passes complete document data including attachments
        # No special handling needed - LLM extraction should capture attachments
        
        # If basic claim info doesn't have attachments, try to fetch from Cosmos DB as fallback
        attachment_fields = ['billAttachment', 'memoAttachment', 'dischargeAttachment']
        has_attachments = any(field in claim_info and claim_info[field] for field in attachment_fields)
        
        if not has_attachments:
            # If orchestrator didn't provide attachments, try to fetch from Cosmos DB as fallback
            try:
                full_claim_data = await self._fetch_complete_claim_data(claim_id)
                if full_claim_data:
                    # Merge full claim data with parsed claim_info
                    claim_info.update(full_claim_data)
                    self.logger.info(f"✅ Retrieved full claim data with attachments for {claim_id}")
                else:
                    self.logger.warning(f"⚠️ Could not retrieve full claim data for {claim_id}, proceeding with basic data")
            except Exception as e:
                self.logger.error(f"❌ Error fetching complete claim data from Cosmos DB: {e}")
                self.logger.warning(f"⚠️ Could not retrieve full claim data for {claim_id}, proceeding with basic data")
        else:
            self.logger.info(f"✅ Using attachment URLs provided by orchestrator for {claim_id}")
        
        # STEP 1: Check document requirements FIRST
        document_check = self._check_document_requirements(claim_info)
        if not document_check["valid"]:
            rejection_reason = document_check["reason"]
            rules_applied.append(f"❌ REJECTED: {rejection_reason}")
            result = await self._create_rejection_result(claim_id, bill_amount, rules_applied, rejection_reason)
            return result
        
        rules_applied.extend(document_check["rules_applied"])
        
        # STEP 2: Validate claim category
        if 'outpatient' in category:
            required_docs = self.rule_sets["document_requirements"]["outpatient"]["required_documents"]
            rules_applied.append(f"✅ Outpatient claim - requires: {', '.join(required_docs)}")
        elif 'inpatient' in category:
            required_docs = self.rule_sets["document_requirements"]["inpatient"]["required_documents"]
            rules_applied.append(f"✅ Inpatient claim - requires: {', '.join(required_docs)}")
        else:
            rejection_reason = f"Invalid claim category: {category}. Must be 'inpatient' or 'outpatient'"
            rules_applied.append(f"❌ {rejection_reason}")
            result = await self._create_rejection_result(claim_id, bill_amount, rules_applied, rejection_reason)
            return result
        
        # STEP 3: Classify claim type based on diagnosis (YOUR SPECIFIC RULES)
        claim_type = self._classify_claim_type(diagnosis)
        claim_limits = self.rule_sets["claim_type_limits"][claim_type]
        max_amount = claim_limits["max_amount"]
        
        rules_applied.append(f"🏷️ Claim classified as: {claim_type.upper()}")
        rules_applied.append(f"💰 Maximum allowed amount: ${max_amount}")
        
        # STEP 4: Validate bill amount against YOUR SPECIFIC LIMITS
        if bill_amount > max_amount:
            rejection_reason = f"Bill amount ${bill_amount} exceeds {claim_type} limit of ${max_amount}"
            rules_applied.append(f"❌ REJECTED: {rejection_reason}")
            result = await self._create_rejection_result(claim_id, bill_amount, rules_applied, rejection_reason)
            return result
        
        # STEP 5: All validations passed - APPROVE for workflow continuation
        rules_applied.append(f"✅ Amount validation passed: ${bill_amount} ≤ ${max_amount}")
        rules_applied.append(f"🔄 APPROVED for next workflow step: Document Intelligence")
        
        return {
            "eligible": True,
            "claim_type": claim_type,
            "max_allowed": max_amount,
            "bill_amount": bill_amount,
            "amount_within_limit": True,
            "required_documents": required_docs,
            "rules_applied": rules_applied,
            "rejection_reason": None,
            "workflow_action": "continue_to_document_intelligence",
            "next_agent": "document_intelligence",
            "status": "approved_for_processing"
        }
        
    async def _fetch_complete_claim_data(self, claim_id: str) -> Dict[str, Any]:
        """
        Fetch complete claim data directly from Cosmos DB including attachment fields
        """
        try:
            if not self.cosmos_client:
                self.logger.warning("⚠️ Cosmos DB client not available, cannot fetch complete claim data")
                return {}
            
            # Get database and container
            async with self.cosmos_client as client:
                database = client.get_database_client(self.database_name)
                container = database.get_container_client(self.container_name)
                
                # Query for the specific claim
                query = "SELECT * FROM c WHERE c.claimId = @claim_id"
                parameters = [{"name": "@claim_id", "value": claim_id}]
                
                items = []
                async for item in container.query_items(query=query, parameters=parameters):
                    items.append(item)
                
                if items:
                    claim_data = items[0]  # Get the first (should be only) result
                    self.logger.info(f"✅ Retrieved complete claim data for {claim_id} directly from Cosmos DB")
                    return claim_data
                else:
                    self.logger.warning(f"⚠️ No claim found with ID {claim_id}")
                    return {}
                
        except Exception as e:
            self.logger.error(f"❌ Error fetching complete claim data from Cosmos DB: {e}")
            return {}
    
    def _classify_claim_type(self, diagnosis: str) -> str:
        """Classify claim type based on diagnosis using LLM for intelligent classification"""
        try:
            # Import Azure OpenAI client
            from openai import AzureOpenAI
            
            # Initialize Azure OpenAI client
            client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            
            # Create classification prompt
            classification_prompt = f"""
Analyze this medical diagnosis and classify it into one of three categories:
- "eye": Eye, vision, or ophthalmology-related conditions
- "dental": Dental, oral, or teeth-related conditions  
- "general": All other medical conditions

Diagnosis: "{diagnosis}"

Return ONLY the category name (eye, dental, or general) with no additional text.
"""
            
            # Call LLM for classification
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini-deployment"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a medical classification expert. Classify medical diagnoses into eye, dental, or general categories. Return only the category name."
                    },
                    {
                        "role": "user",
                        "content": classification_prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=10
            )
            
            # Parse LLM response
            classification_result = response.choices[0].message.content.strip().lower()
            
            # Validate result and provide fallback
            valid_types = ["eye", "dental", "general"]
            if classification_result in valid_types:
                self.logger.info(f"🤖 LLM classified '{diagnosis}' as: {classification_result}")
                return classification_result
            else:
                self.logger.warning(f"⚠️ LLM returned invalid classification '{classification_result}', defaulting to general")
                return "general"
                
        except Exception as e:
            self.logger.error(f"❌ LLM classification failed for '{diagnosis}': {e}")
            self.logger.info(f"🔄 Falling back to keyword-based classification")
            
            # Fallback to keyword-based classification
            return self._classify_claim_type_keywords(diagnosis)
    
    def _classify_claim_type_keywords(self, diagnosis: str) -> str:
        """Fallback keyword-based classification method"""
        diagnosis_lower = diagnosis.lower()
        
        # Check for eye-related conditions
        eye_keywords = self.rule_sets["claim_type_limits"]["eye"]["keywords"]
        if any(keyword in diagnosis_lower for keyword in eye_keywords):
            self.logger.info(f"🔍 Eye condition detected in: {diagnosis}")
            return "eye"
        
        # Check for dental conditions
        dental_keywords = self.rule_sets["claim_type_limits"]["dental"]["keywords"]
        if any(keyword in diagnosis_lower for keyword in dental_keywords):
            self.logger.info(f"🦷 Dental condition detected in: {diagnosis}")
            return "dental"
        
        # Default to general
        self.logger.info(f"🏥 General medical condition: {diagnosis}")
        return "general"
    
    def _check_document_requirements(self, claim_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if required documents are present for the claim type
        Based on your vision: Outpatient needs bill+memo, Inpatient needs bill+memo+discharge
        """
        category = claim_info.get('category', '').lower()
        
        # DEBUG: Log what we have in claim_info
        self.logger.info(f"🔍 Document check for category: {category}")
        self.logger.info(f"🔍 Available fields in claim_info: {list(claim_info.keys())}")
        self.logger.info(f"🔍 billAttachment: {claim_info.get('billAttachment', 'NOT FOUND')}")
        self.logger.info(f"🔍 memoAttachment: {claim_info.get('memoAttachment', 'NOT FOUND')}")
        if 'inpatient' in category:
            self.logger.info(f"🔍 dischargeAttachment: {claim_info.get('dischargeAttachment', 'NOT FOUND')}")
        
        # Determine required attachments based on category
        if 'outpatient' in category:
            required_attachments = ['billAttachment', 'memoAttachment']
            required_docs = ['bill', 'memo']
        elif 'inpatient' in category:
            required_attachments = ['billAttachment', 'memoAttachment', 'dischargeAttachment']
            required_docs = ['bill', 'memo', 'discharge summary']
        else:
            return {
                "valid": False,
                "reason": f"Invalid category '{category}'. Must be 'inpatient' or 'outpatient'",
                "rules_applied": []
            }
        
        # Check if all required attachments are present and not empty
        missing_docs = []
        rules_applied = []
        
        for attachment_field, doc_name in zip(required_attachments, required_docs):
            attachment_url = claim_info.get(attachment_field, "")
            if not attachment_url or attachment_url.strip() == "":
                missing_docs.append(doc_name)
            else:
                rules_applied.append(f"✅ {doc_name.title()} document present")
        
        if missing_docs:
            missing_list = ", ".join(missing_docs)
            return {
                "valid": False,
                "reason": f"Insufficient documents for {category} claim. Missing: {missing_list}",
                "rules_applied": rules_applied
            }
        
        # All documents present
        rules_applied.append(f"✅ All required documents present for {category} claim")
        return {
            "valid": True,
            "reason": None,
            "rules_applied": rules_applied
        }
    
    async def _create_rejection_result(self, claim_id: str, bill_amount: float, rules_applied: List[str], rejection_reason: str) -> Dict[str, Any]:
        """Create a standardized rejection result and update status in database"""
        
        # Update status in database for traditional validation failures
        await self._update_claim_status(claim_id, "marked for rejection", rejection_reason)
        
        return {
            "eligible": False,
            "claim_type": "unknown",
            "max_allowed": 0,
            "bill_amount": bill_amount,
            "amount_within_limit": False,
            "required_documents": [],
            "rules_applied": rules_applied,
            "rejection_reason": rejection_reason,
            "workflow_action": "mark_for_rejection",
            "next_agent": None,
            "status": "rejected"
        }

    async def _check_claim_status(self, claim_id: str) -> Dict[str, Any]:
        """
        Check if claim is already approved in claim_details container
        Returns: {"can_process": bool, "reason": str}
        """
        try:
            if not self.cosmos_client:
                self.logger.warning("⚠️ Cosmos DB client not available, skipping status check")
                return {"can_process": True, "reason": "Cosmos client unavailable"}
            
            # Get database and container
            async with self.cosmos_client as client:
                database = client.get_database_client(self.database_name)
                container = database.get_container_client("claim_details")
                
                # Query for the specific claim status
                query = "SELECT c.status FROM c WHERE c.claimId = @claim_id"
                parameters = [{"name": "@claim_id", "value": claim_id}]
                
                items = []
                async for item in container.query_items(query=query, parameters=parameters):
                    items.append(item)
                
                if items:
                    current_status = items[0].get('status', '').lower()
                    self.logger.info(f"🔍 Found claim {claim_id} with status: {current_status}")
                    
                    if current_status == "marked for approval":
                        return {
                            "can_process": False,
                            "reason": "Claim denied - already approved"
                        }
                    
                    return {"can_process": True, "reason": f"Status check passed: {current_status}"}
                else:
                    self.logger.warning(f"⚠️ No claim found with ID {claim_id}")
                    return {"can_process": True, "reason": "Claim not found, allowing processing"}
                
        except Exception as e:
            self.logger.error(f"❌ Error checking claim status: {e}")
            # Default to allowing processing if check fails
            return {"can_process": True, "reason": f"Status check failed: {str(e)}"}

    async def _check_document_processing_status(self, claim_id: str) -> Dict[str, Any]:
        """
        Check if documents are already processed in extracted_patient_data container
        Returns: {"can_process": bool, "reason": str}
        """
        try:
            if not self.cosmos_client:
                self.logger.warning("⚠️ Cosmos DB client not available, skipping document processing check")
                return {"can_process": True, "reason": "Cosmos client unavailable"}
            
            # Get database and container
            async with self.cosmos_client as client:
                database = client.get_database_client(self.database_name)
                container = database.get_container_client("extracted_patient_data")
                
                # Query for existing extracted data with this claim_id
                query = "SELECT c.id FROM c WHERE c.id = @claim_id"
                parameters = [{"name": "@claim_id", "value": claim_id}]
                
                items = []
                async for item in container.query_items(query=query, parameters=parameters):
                    items.append(item)
                
                if items:
                    self.logger.info(f"🔍 Found existing extracted data for claim {claim_id}")
                    return {
                        "can_process": False,
                        "reason": "Claim denied - documents already processed"
                    }
                else:
                    self.logger.info(f"✅ No existing extracted data found for claim {claim_id}")
                    return {"can_process": True, "reason": "Document processing check passed"}
                
        except Exception as e:
            self.logger.error(f"❌ Error checking document processing status: {e}")
            # Default to allowing processing if check fails
            return {"can_process": True, "reason": f"Document processing check failed: {str(e)}"}

    async def _update_claim_status(self, claim_id: str, new_status: str, reason: str = None) -> bool:
        """
        Update claim status in claim_details container
        Returns: True if successful, False otherwise
        """
        try:
            if not self.cosmos_client:
                self.logger.warning("⚠️ Cosmos DB client not available, cannot update status")
                return False
            
            # Get database and container
            async with self.cosmos_client as client:
                database = client.get_database_client(self.database_name)
                container = database.get_container_client("claim_details")
                
                # First, get the existing document
                query = "SELECT * FROM c WHERE c.claimId = @claim_id"
                parameters = [{"name": "@claim_id", "value": claim_id}]
                
                items = []
                async for item in container.query_items(query=query, parameters=parameters):
                    items.append(item)
                
                if not items:
                    self.logger.error(f"❌ Cannot update status: claim {claim_id} not found")
                    return False
                
                # Update the document
                claim_doc = items[0]
                claim_doc['status'] = new_status
                claim_doc['lastUpdatedAt'] = datetime.now().isoformat()
                
                if reason:
                    if 'processing_notes' not in claim_doc:
                        claim_doc['processing_notes'] = []
                    claim_doc['processing_notes'].append({
                        'timestamp': datetime.now().isoformat(),
                        'note': reason,
                        'updated_by': 'coverage_rules_engine'
                    })
                
                # Replace the document
                await container.replace_item(
                    item=claim_doc,
                    body=claim_doc
                )
                
                self.logger.info(f"✅ Updated claim {claim_id} status to: {new_status}")
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Error updating claim status: {e}")
            return False

# Create the fixed executor instance
CoverageRulesExecutor = CoverageRulesExecutorFixed

print("⚖️ FIXED Coverage Rules Engine Executor loaded successfully!")
print("✅ A2A compatible version with correct parameter handling")
