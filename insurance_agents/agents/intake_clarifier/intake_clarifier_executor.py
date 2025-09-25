"""
Intake Clarifier Executor - Updated for Your Vision
Implements verification logic by comparing claim_details vs extracted_patient_data
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.utils import new_agent_text_message

from shared.mcp_config import A2A_AGENT_PORTS
from shared.a2a_client import A2AClient

class IntakeClarifierExecutor(AgentExecutor):
    """
    Intake Clarifier Executor - Updated for Your Vision
    Verifies claims by comparing claim_details vs extracted_patient_data
    """
    
    def __init__(self):
        self.agent_name = "intake_clarifier"
        self.agent_description = "Verifies claims by comparing extracted vs original data"
        self.port = A2A_AGENT_PORTS["intake_clarifier"]
        self.logger = self._setup_logging()
        
        # Initialize A2A client for agent communication
        self.a2a_client = A2AClient(self.agent_name)
        
    def _setup_logging(self) -> logging.Logger:
        """Setup colored logging for the agent"""
        logger = logging.getLogger(f"InsuranceAgent.{self.agent_name}")
        
        # Create colored formatter
        formatter = logging.Formatter(
            f"📋 [INTAKE_CLARIFIER] %(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S"
        )
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        
        return logger

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute verification by comparing claim_details vs extracted_patient_data
        According to YOUR VISION workflow
        """
        try:
            user_input = context.get_user_input()
            self.logger.info(f"� Starting intake verification: {user_input[:100]}...")
            
            # Extract claim ID from the input
            claim_id = await self._extract_claim_id_from_input(user_input)
            
            if not claim_id:
                await self._send_error_response(context, event_queue, "Could not extract claim ID from input")
                return
            
            # Perform verification according to your vision
            verification_result = await self._verify_claim_data(claim_id)
            
            # Update Cosmos DB status based on verification
            await self._update_claim_status(claim_id, verification_result)
            
            # Send response back to orchestrator
            await self._send_verification_response(context, event_queue, claim_id, verification_result)
            
        except Exception as e:
            self.logger.error(f"❌ Execution error: {str(e)}")
            await self._send_error_response(context, event_queue, str(e))

    async def _verify_claim_data(self, claim_id: str) -> Dict[str, Any]:
        """
        Core verification logic according to YOUR VISION:
        1. Fetch claim_details document
        2. Fetch extracted_patient_data document
        3. Compare patient name, bill amount, bill date, diagnosis vs medical condition
        4. Return verification result
        """
        try:
            self.logger.info(f"🔍 Starting verification for claim {claim_id}")
            
            # Step 1: Fetch claim_details document
            claim_details = await self._fetch_claim_details(claim_id)
            if not claim_details:
                return self._create_verification_result(False, "claim_details not found", claim_id)
            
            # Step 2: Fetch extracted_patient_data document
            extracted_data = await self._fetch_extracted_patient_data(claim_id)
            if not extracted_data:
                return self._create_verification_result(False, "extracted_patient_data not found", claim_id)
            
            # Step 3: Perform LLM-based data comparison according to your vision
            comparison_result = await self._llm_compare_claim_vs_extracted_data(claim_details, extracted_data)
            
            # Step 4: Update claim status in Cosmos DB based on verification result
            await self._update_claim_status(claim_id, comparison_result)
            
            self.logger.info(f"✅ Verification completed for {claim_id}: {'PASSED' if comparison_result['verified'] else 'FAILED'}")
            
            return comparison_result
            
        except Exception as e:
            self.logger.error(f"❌ Verification error for {claim_id}: {e}")
            return self._create_verification_result(False, f"verification_error: {str(e)}", claim_id)
    
    async def _handle_claim_clarification(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle claim clarification and validation requests"""
        self.logger.info("📋 Performing claim clarification")
        
        # Extract claim information
        claim_id = parameters.get('claim_id', f"CLARIFY_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        claim_type = parameters.get('claim_type', 'unknown')
        description = parameters.get('description', '')
        documents = parameters.get('documents', [])
        customer_id = parameters.get('customer_id', '')
        
        # Perform clarification analysis
        clarification_result = await self._perform_clarification_analysis({
            'claim_id': claim_id,
            'claim_type': claim_type,
            'description': description,
            'documents': documents,
            'customer_id': customer_id
        })
        
        return {
            "status": "success",
            "claim_id": claim_id,
            "clarification_result": clarification_result,
            "agent": self.agent_name
        }
    
    async def _handle_fraud_assessment(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle fraud risk assessment requests"""
        self.logger.info("🚨 Performing fraud risk assessment")
        
        claim_data = parameters.get('claim_data', {})
        
        # Perform fraud assessment
        fraud_assessment = await self._assess_fraud_risk(claim_data)
        
        return {
            "status": "success",
            "fraud_assessment": fraud_assessment,
            "agent": self.agent_name
        }
    
    async def _handle_status_request(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle status check requests"""
        return {
            "status": "success",
            "agent_status": "running",
            "agent": self.agent_name,
            "port": self.port,
            "timestamp": datetime.now().isoformat(),
            "capabilities": [
                "Validate claim completeness",
                "Assess fraud risk",
                "Generate clarification questions",
                "Check customer information",
                "Score claim quality"
            ]
        }
    
    async def _handle_general_request(self, task: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle general requests"""
        self.logger.info(f"🤖 Handling general request: {task}")
        
        return {
            "status": "success",
            "message": f"Processed task: {task}",
            "task": task,
            "parameters": parameters,
            "agent": self.agent_name,
            "specialties": [
                "Claims validation and clarification",
                "Fraud risk assessment",
                "Customer information verification",
                "Document completeness checking"
            ]
        }
    
    async def _perform_clarification_analysis(self, claim_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform comprehensive claim clarification analysis"""
        claim_id = claim_data['claim_id']
        self.logger.info(f"🔍 Analyzing claim for clarification: {claim_id}")
        
        clarification_result = {
            "claim_id": claim_id,
            "validation_status": "pending",
            "completeness_score": 0,
            "fraud_risk_score": 0,
            "issues": [],
            "questions": [],
            "recommendations": []
        }
        
        try:
            # Check required fields
            required_fields = ['claim_id', 'claim_type', 'customer_id', 'description']
            missing_fields = [field for field in required_fields if not claim_data.get(field)]
            
            if missing_fields:
                clarification_result["issues"].extend(missing_fields)
                clarification_result["questions"].extend([
                    f"Please provide {field.replace('_', ' ')}" for field in missing_fields
                ])
            
            # Calculate completeness score
            total_fields = ['claim_id', 'claim_type', 'customer_id', 'description', 'documents']
            provided_fields = [field for field in total_fields if claim_data.get(field)]
            clarification_result["completeness_score"] = int((len(provided_fields) / len(total_fields)) * 100)
            
            # Assess description quality
            description = claim_data.get('description', '')
            if len(description) < 20:
                clarification_result["issues"].append("insufficient_description")
                clarification_result["questions"].append("Can you provide more detailed description?")
            
            # Calculate fraud risk
            clarification_result["fraud_risk_score"] = self._calculate_fraud_risk(claim_data)
            
            # Determine validation status
            if missing_fields or clarification_result["fraud_risk_score"] > 70:
                clarification_result["validation_status"] = "requires_clarification"
            elif clarification_result["completeness_score"] < 60:
                clarification_result["validation_status"] = "incomplete"
            else:
                clarification_result["validation_status"] = "validated"
            
            # Generate recommendations
            if clarification_result["validation_status"] == "validated":
                clarification_result["recommendations"].append("Proceed to document analysis")
            else:
                clarification_result["recommendations"].append("Address validation issues before proceeding")
            
            self.logger.info(f"✅ Clarification completed: {clarification_result['validation_status']}")
            
            return clarification_result
            
        except Exception as e:
            self.logger.error(f"❌ Clarification analysis failed: {str(e)}")
            clarification_result["validation_status"] = "error"
            clarification_result["issues"].append(f"Analysis error: {str(e)}")
            return clarification_result
    
    async def _assess_fraud_risk(self, claim_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess fraud risk for a claim"""
        self.logger.info("🚨 Assessing fraud risk")
        
        fraud_score = self._calculate_fraud_risk(claim_data)
        
        risk_level = "low"
        if fraud_score > 70:
            risk_level = "high"
        elif fraud_score > 40:
            risk_level = "medium"
        
        return {
            "fraud_score": fraud_score,
            "risk_level": risk_level,
            "factors": self._get_fraud_factors(claim_data),
            "recommendations": self._get_fraud_recommendations(fraud_score)
        }
    
    def _get_fraud_factors(self, claim_data: Dict[str, Any]) -> List[str]:
        """Get factors contributing to fraud risk"""
        factors = []
        
        description = claim_data.get('description', '').lower()
        
        if len(description) < 10:
            factors.append("Very brief claim description")
        
        if 'total loss' in description:
            factors.append("Total loss claim")
        
        if not claim_data.get('documents'):
            factors.append("No supporting documents provided")
        
        return factors
    
    def _get_fraud_recommendations(self, fraud_score: int) -> List[str]:
        """Get recommendations based on fraud score"""
        recommendations = []
        
        if fraud_score > 70:
            recommendations.extend([
                "Flag for manual fraud investigation",
                "Request additional documentation",
                "Verify customer identity"
            ])
        elif fraud_score > 40:
            recommendations.extend([
                "Increase documentation requirements",
                "Perform additional validation checks"
            ])
        else:
            recommendations.append("Standard processing approved")
    
    async def _handle_a2a_claim_clarification(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle A2A claim clarification requests from Claims Orchestrator
        
        Args:
            parameters: Contains claim_data from orchestrator
            
        Returns:
            Clarified claim data
        """
        try:
            self.logger.info("📨 Handling A2A claim clarification request")
            
            claim_data = parameters.get('claim_data', {})
            claim_id = claim_data.get('claim_id', 'UNKNOWN')
            
            # Use MCP to check existing claims data
            self.logger.info(f"🔍 Checking existing claims for {claim_id} using MCP...")
            existing_claims = await self.mcp_client.get_claims(claim_id)
            
            # Perform clarification analysis
            clarified_data = await self._clarify_claim_data(claim_data)
            
            # Perform completeness check
            completeness_score = self._calculate_completeness_score(clarified_data)
            
            # Perform fraud risk assessment
            fraud_risk_score = self._calculate_fraud_risk(clarified_data)
            
            self.logger.info(f"✅ Claim clarification completed for {claim_id}")
            
            return {
                "status": "completed",
                "clarified_data": clarified_data,
                "completeness_score": completeness_score,
                "fraud_risk_score": fraud_risk_score,
                "validation_status": "validated" if completeness_score > 70 else "incomplete",
                "agent": self.agent_name,
                "processing_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"❌ A2A clarification error: {str(e)}")
            return {
                "status": "failed",
                "error": str(e),
                "agent": self.agent_name
            }
    
    async def _clarify_claim_data(self, claim_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clarify and enhance claim data
        
        Args:
            claim_data: Raw claim data
            
        Returns:
            Clarified claim data
        """
        clarified = claim_data.copy()
        
        # Add standardized fields
        clarified['claim_type_standardized'] = self._standardize_claim_type(claim_data.get('type', ''))
        clarified['amount_numeric'] = self._extract_numeric_amount(claim_data.get('amount', 0))
        clarified['date_standardized'] = self._standardize_date(claim_data.get('date', ''))
        
        # Add derived fields
        clarified['urgency_level'] = self._determine_urgency(clarified)
        clarified['complexity_score'] = self._calculate_complexity(clarified)
        
        return clarified
    
    def _standardize_claim_type(self, claim_type: str) -> str:
        """Standardize claim type"""
        claim_type_lower = claim_type.lower()
        if 'auto' in claim_type_lower or 'vehicle' in claim_type_lower:
            return 'automotive'
        elif 'home' in claim_type_lower or 'property' in claim_type_lower:
            return 'property'
        elif 'health' in claim_type_lower or 'medical' in claim_type_lower:
            return 'medical'
        else:
            return 'general'
    
    def _extract_numeric_amount(self, amount) -> float:
        """Extract numeric amount from various formats"""
        if isinstance(amount, (int, float)):
            return float(amount)
        elif isinstance(amount, str):
            # Remove currency symbols and extract number
            import re
            numbers = re.findall(r'[\d,]+\.?\d*', amount.replace(',', ''))
            return float(numbers[0]) if numbers else 0.0
        else:
            return 0.0
    
    def _standardize_date(self, date_str) -> str:
        """Standardize date format"""
        if not date_str:
            return datetime.now().isoformat()
        # In a real implementation, this would handle various date formats
        return str(date_str)
    
    def _determine_urgency(self, claim_data: Dict[str, Any]) -> str:
        """Determine claim urgency level"""
        amount = claim_data.get('amount_numeric', 0)
        claim_type = claim_data.get('claim_type_standardized', '')
        
        if amount > 100000 or claim_type == 'medical':
            return 'high'
        elif amount > 10000:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_complexity(self, claim_data: Dict[str, Any]) -> int:
        """Calculate claim complexity score (1-10)"""
        complexity = 1
        
        # Add complexity based on various factors
        if claim_data.get('documents'):
            complexity += len(claim_data['documents'])
        
        if claim_data.get('amount_numeric', 0) > 50000:
            complexity += 3
        
        if claim_data.get('claim_type_standardized') == 'medical':
            complexity += 2
        
        return min(complexity, 10)
    
    def _calculate_completeness_score(self, claim_data: Dict[str, Any]) -> int:
        """Calculate how complete the claim data is (0-100)"""
        required_fields = ['claim_id', 'type', 'amount', 'description']
        optional_fields = ['customer_id', 'date', 'documents', 'policy_number']
        
        score = 0
        
        # Check required fields
        for field in required_fields:
            if claim_data.get(field):
                score += 20
        
        # Check optional fields
        for field in optional_fields:
            if claim_data.get(field):
                score += 5
        
        return min(score, 100)
    
    def _calculate_fraud_risk(self, claim_data: Dict[str, Any]) -> int:
        """Calculate fraud risk score (0-100)"""
        risk = 0
        
        # High amount increases risk
        amount = claim_data.get('amount_numeric', 0)
        if amount > 100000:
            risk += 30
        elif amount > 50000:
            risk += 15
        
        # Multiple claims in short time (mock check)
        risk += 10  # Simplified risk calculation
        
        return min(risk, 100)
    
    async def _fetch_claim_details(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """Fetch claim_details document from Cosmos DB"""
        try:
            result = await self.mcp_client.execute_tool(
                "cosmos_query",
                {
                    "container": "claim_details",
                    "query": f"SELECT * FROM c WHERE c.id = '{claim_id}'"
                }
            )
            
            if result and len(result) > 0:
                self.logger.info(f"✅ Found claim_details for {claim_id}")
                return result[0]
            else:
                self.logger.warning(f"⚠️ No claim_details found for {claim_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error fetching claim_details for {claim_id}: {e}")
            return None
    
    async def _fetch_extracted_patient_data(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """Fetch extracted_patient_data document from Cosmos DB"""
        try:
            result = await self.mcp_client.execute_tool(
                "cosmos_query",
                {
                    "container": "extracted_patient_data",
                    "query": f"SELECT * FROM c WHERE c.id = '{claim_id}'"
                }
            )
            
            if result and len(result) > 0:
                self.logger.info(f"✅ Found extracted_patient_data for {claim_id}")
                return result[0]
            else:
                self.logger.warning(f"⚠️ No extracted_patient_data found for {claim_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error fetching extracted_patient_data for {claim_id}: {e}")
            return None
    
    async def _llm_compare_claim_vs_extracted_data(self, claim_details: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use LLM to intelligently compare claim_details vs extracted_patient_data
        According to YOUR VISION: Compare patient name, bill amount, bill date, diagnosis vs medical condition
        """
        try:
            # Import Azure OpenAI client
            from openai import AzureOpenAI
            import os
            from dotenv import load_dotenv
            
            # Load environment variables
            load_dotenv()
            
            # Initialize Azure OpenAI client
            client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            
            # Create comparison prompt
            comparison_prompt = self._create_llm_comparison_prompt(claim_details, extracted_data)
            
            # Call LLM for intelligent comparison
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini-deployment"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert insurance claim verifier. Compare original claim data with extracted document data to identify discrepancies. Be precise and only flag genuine mismatches. Return ONLY valid JSON."
                    },
                    {
                        "role": "user",
                        "content": comparison_prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent verification
                max_tokens=800
            )
            
            # Parse LLM response
            llm_result = response.choices[0].message.content.strip()
            
            # Clean and parse JSON response
            if llm_result.startswith("```json"):
                llm_result = llm_result.replace("```json", "").replace("```", "").strip()
            
            comparison_result = json.loads(llm_result)
            
            self.logger.info(f"🤖 LLM verification completed: {'VERIFIED' if comparison_result.get('verified', False) else 'REJECTED'}")
            return comparison_result
            
        except Exception as e:
            self.logger.error(f"❌ LLM comparison failed: {e}")
            # Fallback to manual comparison if LLM fails
            return self._fallback_manual_comparison(claim_details, extracted_data)
    
    def _create_llm_comparison_prompt(self, claim_details: Dict[str, Any], extracted_data: Dict[str, Any]) -> str:
        """Create intelligent comparison prompt for LLM"""
        
        # Extract key fields from claim_details
        original_patient = claim_details.get('patientName', '')
        original_bill_amount = claim_details.get('billAmount', 0)
        original_bill_date = claim_details.get('billDate', '')
        original_diagnosis = claim_details.get('diagnosis', '')
        
        # Extract fields from extracted documents (smart extraction)
        extracted_patient_names = []
        extracted_bill_amounts = []
        extracted_bill_dates = []
        extracted_conditions = []
        
        # Extract from medical_bill_doc
        if 'medical_bill_doc' in extracted_data:
            bill_doc = extracted_data['medical_bill_doc']
            if bill_doc.get('patient_name'):
                extracted_patient_names.append(bill_doc['patient_name'])
            if bill_doc.get('bill_amount'):
                extracted_bill_amounts.append(bill_doc['bill_amount'])
            if bill_doc.get('bill_date'):
                extracted_bill_dates.append(bill_doc['bill_date'])
        
        # Extract from memo_doc
        if 'memo_doc' in extracted_data:
            memo_doc = extracted_data['memo_doc']
            if memo_doc.get('patient_name'):
                extracted_patient_names.append(memo_doc['patient_name'])
            if memo_doc.get('medical_condition'):
                extracted_conditions.append(memo_doc['medical_condition'])
        
        # Extract from discharge_summary_doc (if inpatient)
        if 'discharge_summary_doc' in extracted_data:
            discharge_doc = extracted_data['discharge_summary_doc']
            if discharge_doc.get('patient_name'):
                extracted_patient_names.append(discharge_doc['patient_name'])
            if discharge_doc.get('medical_condition'):
                extracted_conditions.append(discharge_doc['medical_condition'])
        
        return f"""
Compare the original claim data with extracted document data and verify if they match.

ORIGINAL CLAIM DATA:
- Patient Name: "{original_patient}"
- Bill Amount: {original_bill_amount}
- Bill Date: "{original_bill_date}"
- Diagnosis: "{original_diagnosis}"

EXTRACTED DOCUMENT DATA:
- Patient Names Found: {extracted_patient_names}
- Bill Amounts Found: {extracted_bill_amounts}
- Bill Dates Found: {extracted_bill_dates}
- Medical Conditions Found: {extracted_conditions}

VERIFICATION REQUIREMENTS:
1. Patient names should match (allow for minor variations like "John Doe" vs "John A. Doe")
2. Bill amounts should match exactly or very closely
3. Bill dates should match (allow for different date formats)
4. Diagnosis should match medical conditions (allow for medical terminology variations)

Return JSON with this exact format:
{{
    "verified": true/false,
    "reason": "explanation of verification result",
    "mismatches": [
        {{
            "field": "field_name",
            "original_value": "value_from_claim",
            "extracted_value": "value_from_documents",
            "severity": "high/medium/low"
        }}
    ],
    "overall_confidence": "high/medium/low",
    "recommendation": "approve/reject"
}}

Be intelligent about minor variations but flag genuine discrepancies.
"""
    
    def _fallback_manual_comparison(self, claim_details: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback manual comparison if LLM fails"""
        # Simple fallback comparison
        mismatches = []
        
        # Basic name comparison
        original_patient = claim_details.get('patientName', '').lower()
        extracted_names = []
        
        if 'medical_bill_doc' in extracted_data and extracted_data['medical_bill_doc'].get('patient_name'):
            extracted_names.append(extracted_data['medical_bill_doc']['patient_name'].lower())
        
        if extracted_names and not any(original_patient in name or name in original_patient for name in extracted_names):
            mismatches.append({
                "field": "patient_name",
                "original_value": claim_details.get('patientName', ''),
                "extracted_value": extracted_names[0] if extracted_names else '',
                "severity": "high"
            })
        
        verified = len(mismatches) == 0
        
        return {
            "verified": verified,
            "reason": "Fallback manual comparison completed",
            "mismatches": mismatches,
            "overall_confidence": "low",
            "recommendation": "approve" if verified else "reject"
        }
    
    async def _update_claim_status(self, claim_id: str, verification_result: Dict[str, Any]) -> None:
        """Update claim status in Cosmos DB based on verification result"""
        try:
            # Determine new status based on verification
            if verification_result.get('verified', False):
                new_status = "marked for approval"
                self.logger.info(f"✅ Claim {claim_id} marked for approval")
            else:
                new_status = "marked for rejection"
                reason = verification_result.get('reason', 'Verification failed')
                self.logger.info(f"❌ Claim {claim_id} marked for rejection: {reason}")
            
            # Update status in claim_details container
            await self.mcp_client.execute_tool(
                "cosmos_update",
                {
                    "container": "claim_details",
                    "document_id": claim_id,
                    "updates": {
                        "status": new_status,
                        "lastUpdatedAt": datetime.now().isoformat(),
                        "verificationResult": verification_result
                    }
                }
            )
            
            self.logger.info(f"📝 Updated claim {claim_id} status to: {new_status}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to update claim status for {claim_id}: {e}")
    
    def _create_verification_result(self, verified: bool, reason: str, claim_id: str) -> Dict[str, Any]:
        """Create standardized verification result"""
        return {
            "verified": verified,
            "reason": reason,
            "claim_id": claim_id,
            "timestamp": datetime.now().isoformat(),
            "mismatches": [],
            "overall_confidence": "low" if not verified else "medium",
            "recommendation": "approve" if verified else "reject"
        }
    
    async def _extract_claim_id_from_input(self, user_input: str) -> Optional[str]:
        """Extract claim ID from user input using LLM"""
        try:
            # Simple regex patterns first
            import re
            patterns = [
                r'claim[_\s]*(?:id[_\s]*)?[:\s]*([A-Z]{2}-\d+)',
                r'([A-Z]{2}-\d+)',
                r'claim[_\s]+([A-Z0-9-]+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, user_input, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            # If no pattern match, could use LLM for extraction
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Error extracting claim ID: {e}")
            return None
    
    async def _send_verification_response(self, context: RequestContext, event_queue: EventQueue, claim_id: str, verification_result: Dict[str, Any]) -> None:
        """Send verification response back to orchestrator"""
        try:
            if verification_result.get('verified', False):
                message = f"✅ Claim {claim_id} has been verified and marked for approval. Documents have been verified successfully."
            else:
                reason = verification_result.get('reason', 'Unknown verification failure')
                message = f"❌ Claim {claim_id} verification failed and marked for rejection. Reason: {reason}"
            
            # Send response
            response_message = new_agent_text_message(message)
            await event_queue.send_message(response_message)
            
            self.logger.info(f"📤 Sent verification response for {claim_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to send verification response: {e}")
    
    async def _send_error_response(self, context: RequestContext, event_queue: EventQueue, error_message: str) -> None:
        """Send error response"""
        try:
            message = f"❌ Intake verification error: {error_message}"
            response_message = new_agent_text_message(message)
            await event_queue.send_message(response_message)
        except Exception as e:
            self.logger.error(f"❌ Failed to send error response: {e}")

    async def cancel(self):
        """Cancel any ongoing operations"""
        self.logger.info("🛑 Cancelling intake clarifier operations")
        await self.cleanup()

    async def cleanup(self):
        """Cleanup resources"""
        try:
            await self.mcp_client.close()
            self.logger.info("🧹 Resources cleaned up successfully")
        except Exception as e:
            self.logger.error(f"❌ Error during cleanup: {str(e)}")
