"""
Document Intelligence Executor - Implements your specific workflow
Processes documents using Azure Document Intelligence and creates structured data
"""

import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime
import json
import os
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.utils import new_agent_text_message

from shared.mcp_config import A2A_AGENT_PORTS
from shared.a2a_client import A2AClient
from azure.cosmos import CosmosClient

class DocumentIntelligenceExecutor(AgentExecutor):
    """
    Document Intelligence Executor - Processes documents and writes directly to Cosmos DB
    """
    
    def __init__(self):
        self.agent_name = "document_intelligence"
        self.agent_description = "Processes documents using Azure Document Intelligence for insurance claims"
        self.port = A2A_AGENT_PORTS["document_intelligence"]
        self.logger = self._setup_logging()
        
        # Initialize clients
        self.a2a_client = A2AClient(self.agent_name)
        
        # Initialize Azure Document Intelligence client
        self._init_azure_document_intelligence()
        
        # Initialize direct Cosmos DB client
        self._init_cosmos_client()
        
    def _setup_logging(self) -> logging.Logger:
        """Setup colored logging for the agent"""
        logger = logging.getLogger(f"InsuranceAgent.{self.agent_name}")
        
        formatter = logging.Formatter(
            f"📄 [DOCUMENT_INTELLIGENCE] %(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S"
        )
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        
        return logger
    
    def _init_azure_document_intelligence(self):
        """Initialize Azure Document Intelligence client from environment variables"""
        try:
            endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
            key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
            
            if not endpoint or not key:
                self.logger.warning("⚠️ Azure Document Intelligence credentials not found in environment")
                self.document_intelligence_client = None
                return
            
            # Initialize the real Azure Document Intelligence client
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
            
            self.document_intelligence_client = DocumentIntelligenceClient(
                endpoint=endpoint, 
                credential=AzureKeyCredential(key)
            )
            self.logger.info("✅ Azure Document Intelligence client initialized successfully")
            
        except ImportError as e:
            self.logger.error(f"❌ Azure Document Intelligence SDK not installed: {e}")
            self.logger.info("💡 Install with: pip install azure-ai-documentintelligence")
            self.document_intelligence_client = None
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Azure Document Intelligence: {e}")
            self.document_intelligence_client = None

    def _init_cosmos_client(self):
        """Initialize direct Cosmos DB client"""
        try:
            endpoint = os.getenv("COSMOS_ENDPOINT")
            key = os.getenv("COSMOS_KEY")
            database_name = os.getenv("COSMOS_DATABASE_NAME", "insurance_claims")
            
            if not endpoint or not key:
                self.logger.error("❌ Cosmos DB credentials not found in environment")
                self.cosmos_client = None
                return
            
            # Initialize direct Cosmos DB client
            try:
                from azure.cosmos import CosmosClient
                self.cosmos_client = CosmosClient(endpoint, key)
                self.cosmos_database = self.cosmos_client.get_database_client(database_name)
                self.logger.info("✅ Direct Cosmos DB client initialized successfully")
            except ImportError:
                self.logger.warning("⚠️ Azure Cosmos SDK not available, using simulation mode")
                self.cosmos_client = None
                
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Cosmos DB client: {e}")
            self.cosmos_client = None

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute document intelligence processing for your specific workflow
        """
        try:
            user_input = context.get_user_input()
            self.logger.info(f"🔄 Processing request: {user_input[:100]}...")
            self.logger.info(f"📨 FULL REQUEST RECEIVED: {user_input}")
            
            # Process the document intelligence task based on your workflow
            result = await self._process_claim_documents(user_input)
            
            # Send response message
            response_message = new_agent_text_message(
                text=result.get("response", "Document processing completed"),
                task_id=getattr(context, 'task_id', None)
            )
            await event_queue.enqueue_event(response_message)
            
            self.logger.info("✅ Document Intelligence processing completed")
            
        except Exception as e:
            self.logger.error(f"❌ Execution error: {str(e)}")
            
            error_message = new_agent_text_message(
                text=f"Document Intelligence error: {str(e)}",
                task_id=getattr(context, 'task_id', None)
            )
            await event_queue.enqueue_event(error_message)
    
    async def cancel(self, task_id: str) -> None:
        """Cancel a running task"""
        self.logger.info(f"🚫 Cancelling task: {task_id}")
        pass

    async def _process_claim_documents(self, task_text: str) -> Dict[str, Any]:
        """
        Process claim documents according to orchestrator architecture:
        1. Extract claim ID and document URLs from orchestrator request
        2. Check if already processed in extracted_patient_data  
        3. Process documents with Azure Document Intelligence
        4. Write directly to Cosmos DB extracted_patient_data container
        """
        try:
            # Extract claim ID from the request
            claim_id = self._extract_claim_id(task_text)
            if not claim_id:
                return {"status": "error", "response": "No claim ID found in request"}
            
            self.logger.info(f"📋 Processing documents for claim: {claim_id}")
            
            # Extract document URLs from orchestrator request
            self.logger.info(f"🔍 Extracting document URLs from task text...")
            self.logger.info(f"📝 Task text received: {task_text}")
            
            document_urls = self._extract_document_urls_from_request(task_text)
            self.logger.info(f"📎 Extracted {len(document_urls)} document URLs: {document_urls}")
            
            if not document_urls:
                self.logger.error("❌ No document URLs found in orchestrator request")
                self.logger.info("🔄 Attempting direct Cosmos DB lookup for document URLs")
                
                # Fallback Strategy: Direct Cosmos DB lookup
                try:
                    if self.cosmos_client:
                        container = self.cosmos_database.get_container_client("claim_details")
                        query = f"SELECT c.billAttachment, c.memoAttachment, c.dischargeAttachment FROM c WHERE c.claimId = '{claim_id}'"
                        items = list(container.query_items(query=query, enable_cross_partition_query=True))
                        
                        if items:
                            cosmos_urls = []
                            item = items[0]
                            if item.get('billAttachment'):
                                cosmos_urls.append(item['billAttachment'])
                            if item.get('memoAttachment'):
                                cosmos_urls.append(item['memoAttachment'])
                            if item.get('dischargeAttachment'):
                                cosmos_urls.append(item['dischargeAttachment'])
                            
                            if cosmos_urls:
                                self.logger.info(f"✅ Found {len(cosmos_urls)} URLs from Cosmos DB")
                                document_urls = cosmos_urls
                                for url in document_urls:
                                    self.logger.info(f"🔗 Cosmos URL: {url}")
                            else:
                                self.logger.warning("⚠️ Claim found in Cosmos but no attachment URLs")
                        else:
                            self.logger.warning(f"⚠️ Claim {claim_id} not found in Cosmos DB")
                    
                    # Final fallback: Generate expected URLs based on claim ID pattern
                    if not document_urls:
                        self.logger.info("🔄 Final fallback: Generating expected document URLs")
                        category = claim_info.get('category', 'Outpatient').lower()
                        base_url = f"https://captainpstorage1120d503b.blob.core.windows.net/{category}s/{claim_id}"
                        document_urls = [
                            f"{base_url}/{claim_id}_Medical_Bill.pdf",
                            f"{base_url}/{claim_id}_Memo.pdf"
                        ]
                        if category == 'inpatient':
                            document_urls.append(f"{base_url}/{claim_id}_Discharge_Summary.pdf")
                        
                        self.logger.info(f"📎 Generated {len(document_urls)} expected URLs")
                        for url in document_urls:
                            self.logger.info(f"🔗 Generated URL: {url}")
                        
                except Exception as cosmos_error:
                    self.logger.error(f"❌ Cosmos DB lookup failed: {cosmos_error}")
                
                # If still no URLs after all fallbacks, return error
                if not document_urls:
                    return {"status": "error", "response": "Unable to locate document URLs after all fallback attempts"}
            
            # Check if already processed
            if await self._is_already_processed_direct(claim_id):
                self.logger.info(f"⚠️ Claim {claim_id} already processed, skipping")
                return {
                    "status": "skipped",
                    "response": f"Claim {claim_id} documents already processed"
                }
            
            # Extract basic claim info from orchestrator request
            claim_info = self._extract_claim_info_from_request(task_text)
            
            # Process each document with Azure Document Intelligence
            self.logger.info(f"🚀 Starting document processing with Azure Document Intelligence...")
            self.logger.info(f"📊 Document Intelligence client status: {'✅ Available' if self.document_intelligence_client else '❌ Not initialized'}")
            
            try:
                extracted_data = await self._process_documents_with_azure_di(document_urls, claim_info)
                self.logger.info(f"📄 Document processing completed. Extracted data: {extracted_data}")
                
                # Write directly to Cosmos DB extracted_patient_data container
                self.logger.info(f"💾 Writing extracted data to Cosmos DB...")
                await self._write_extracted_data_to_cosmos(claim_id, claim_info, extracted_data)
                self.logger.info(f"✅ Successfully wrote extracted data to Cosmos DB")
                
                # NEW REQUIREMENT: Call intake clarifier after successful document processing
                self.logger.info(f"📋 Calling intake clarifier for verification...")
                intake_result = await self._call_intake_clarifier(claim_id)
                
                if intake_result.get("status") == "success":
                    response = f"""📄 **Document Intelligence Processing Complete**

**Claim ID**: {claim_id}
**Category**: {claim_info.get('category', 'Unknown')}
**Documents Processed**: {len(document_urls)}
**Status**: Successfully processed and stored in extracted_patient_data

**Verification Result**: {intake_result.get('message', 'Intake verification completed')}

**Next Step**: Workflow complete - status updated in Cosmos DB"""
                    
                    return {"status": "success", "response": response}
                else:
                    # Intake clarifier failed, but document processing succeeded
                    response = f"""📄 **Document Intelligence Processing Complete with Verification Issue**

**Claim ID**: {claim_id}
**Category**: {claim_info.get('category', 'Unknown')}
**Documents Processed**: {len(document_urls)}
**Document Status**: Successfully processed and stored in extracted_patient_data
**Verification Status**: Failed - {intake_result.get('message', 'Intake verification failed')}

**Next Step**: Manual review required"""
                    
                    return {"status": "warning", "response": response}
                
            except Exception as doc_error:
                self.logger.error(f"❌ Document processing failed for {claim_id}: {str(doc_error)}")
                
                # Return a clear error message about what failed
                error_response = f"""❌ **Document Intelligence Processing Failed**

**Claim ID**: {claim_id}
**Error**: {str(doc_error)}

**Possible Causes**:
- Azure Document Intelligence service not configured
- Network connectivity issues
- Invalid document URLs
- Missing environment variables

**Status**: Failed - claim cannot proceed to intake clarifier"""
                
                return {"status": "error", "response": error_response}
            
        except Exception as e:
            self.logger.error(f"❌ Error processing claim documents: {e}")
            return {"status": "error", "response": f"Document processing failed: {str(e)}"}
    
    def _extract_claim_id(self, text: str) -> str:
        """Extract claim ID from text"""
        # More flexible pattern to match different claim ID formats
        patterns = [
            r'claim[_\s]*id[:\s]+([A-Z0-9_-]+)',  # CLAIM_TEST_001 format
            r'claim[_\s]*id[:\s]+([A-Z]{2}-\d{2,3})',  # AB-123 format
            r'claim[:\s]+([A-Z0-9_-]+)',  # claim: CLAIM_TEST_001
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None

    def _extract_document_urls_from_request(self, text: str) -> List[str]:
        """Extract document URLs from orchestrator request using LLM"""
        urls = []
        
        try:
            # Use LLM to intelligently extract document URLs
            urls = self._extract_document_urls_with_llm(text)
            self.logger.info(f"📎 LLM extracted {len(urls)} document URLs: {urls}")
            
        except Exception as e:
            self.logger.error(f"❌ LLM URL extraction failed: {e}")
            # Fallback to simple regex as backup
            self.logger.info("🔄 Falling back to regex extraction...")
            url_pattern = r'https?://[^\s]+\.(?:pdf|jpg|jpeg|png|tiff|bmp)'
            urls = re.findall(url_pattern, text, re.IGNORECASE)
            self.logger.info(f"📎 Regex extracted {len(urls)} document URLs: {urls}")
        
        return list(set(urls))  # Remove duplicates
    
    def _extract_document_urls_with_llm(self, text: str) -> List[str]:
        """Use Azure OpenAI to intelligently extract document URLs from text"""
        try:
            from openai import AzureOpenAI
            
            # Initialize Azure OpenAI client
            client = AzureOpenAI(
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
            )
            
            # Create a prompt for URL extraction
            extraction_prompt = f"""
Extract all document URLs from the following text. Look for:
- Full HTTP/HTTPS URLs ending in .pdf, .jpg, .jpeg, .png, .tiff, .bmp
- Blob storage URLs
- Any attachment URLs mentioned

Text to analyze:
{text}

Return ONLY a JSON array of URLs, no other text. Example format:
["https://example.com/doc1.pdf", "https://example.com/doc2.pdf"]

If no URLs found, return: []
"""

            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
                messages=[
                    {"role": "system", "content": "You are a precise document URL extractor. Return only valid JSON arrays of URLs."},
                    {"role": "user", "content": extraction_prompt}
                ],
                max_tokens=500,
                temperature=0
            )
            
            result_text = response.choices[0].message.content.strip()
            self.logger.info(f"🧠 LLM extraction result: {result_text}")
            
            # Clean up the response - remove markdown code blocks if present
            if result_text.startswith('```json'):
                result_text = result_text.replace('```json', '').replace('```', '').strip()
            elif result_text.startswith('```'):
                result_text = result_text.replace('```', '').strip()
            
            # Parse the JSON response
            import json
            urls = json.loads(result_text)
            
            if isinstance(urls, list):
                # Filter out invalid URLs and ensure they're strings
                valid_urls = []
                for url in urls:
                    if isinstance(url, str) and (url.startswith('http://') or url.startswith('https://')):
                        valid_urls.append(url)
                
                self.logger.info(f"📎 LLM successfully extracted {len(valid_urls)} valid URLs")
                return valid_urls
            else:
                self.logger.warning("⚠️ LLM returned non-list response")
                return []
                
        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Failed to parse LLM JSON response: {e}")
            return []
        except Exception as e:
            self.logger.error(f"❌ LLM URL extraction error: {e}")
            return []

    def _extract_claim_info_from_request(self, text: str) -> Dict[str, Any]:
        """Extract basic claim information from orchestrator request"""
        claim_info = {}
        
        # Extract category
        category_match = re.search(r'category[:\s]+(\w+)', text, re.IGNORECASE)
        if category_match:
            claim_info['category'] = category_match.group(1)
        
        # Extract patient name
        patient_match = re.search(r'patient[:\s]+([^\n]+)', text, re.IGNORECASE)
        if patient_match:
            claim_info['patient_name'] = patient_match.group(1).strip()
        
        # Extract diagnosis
        diagnosis_match = re.search(r'diagnosis[:\s]+([^\n]+)', text, re.IGNORECASE)
        if diagnosis_match:
            claim_info['diagnosis'] = diagnosis_match.group(1).strip()
        
        # Extract bill amount
        amount_match = re.search(r'amount[:\s]+\$?([0-9,.]+)', text, re.IGNORECASE)
        if amount_match:
            claim_info['bill_amount'] = float(amount_match.group(1).replace(',', ''))
        
        return claim_info
    
    async def _is_already_processed_direct(self, claim_id: str) -> bool:
        """Check if claim is already processed in extracted_patient_data using direct Cosmos DB access"""
        try:
            if not self.cosmos_client:
                self.logger.warning("⚠️ Cosmos client not available, assuming not processed")
                return False
                
            container = self.cosmos_database.get_container_client("extracted_patient_data")
            query = f"SELECT * FROM c WHERE c.id = '{claim_id}'"
            items = list(container.query_items(query=query, enable_cross_partition_query=True))
            return len(items) > 0
        except Exception as e:
            self.logger.warning(f"⚠️ Error checking if processed: {e}")
            return False

    async def _write_extracted_data_to_cosmos(self, claim_id: str, claim_info: Dict[str, Any], extracted_data: Dict[str, Any]) -> None:
        """Write extracted data directly to Cosmos DB extracted_patient_data container in the correct format"""
        if not self.cosmos_client:
            raise Exception("❌ Cosmos DB client not initialized - cannot write extracted data. Check environment variables: COSMOS_DB_ENDPOINT, COSMOS_DB_KEY")
        
        self.logger.info(f"📝 CONSTRUCTING DOCUMENT for claim {claim_id}")
        self.logger.info(f"📋 Input claim_info: {claim_info}")
        self.logger.info(f"📋 Input extracted_data: {extracted_data}")
        
        # Create the document in the EXACT format provided by user
        extracted_document = {
            "id": claim_id,
            "claimId": claim_id,
            "extractedAt": datetime.now().isoformat() + "+00:00",
            "extractionSource": "Azure Document Intelligence"
        }
        
        self.logger.info(f"📄 Base document structure created: {extracted_document}")
        
        # Add document-specific data based on what was extracted
        # The extracted_data contains data organized by document type
        
        # For each document type, add the structured data - FAIL FAST if extraction failed
        if "medical_bill_doc" in extracted_data:
            bill_extracted = extracted_data["medical_bill_doc"]
            if isinstance(bill_extracted, dict) and "error" in bill_extracted:
                raise Exception(f"❌ Medical bill extraction failed: {bill_extracted['error']}")
            
            if not isinstance(bill_extracted, dict):
                raise Exception(f"❌ Medical bill extraction returned invalid data type: {type(bill_extracted)}")
            
            # Ensure required fields are present
            required_fields = ['patient_name', 'bill_date', 'bill_amount']
            missing_fields = [field for field in required_fields if field not in bill_extracted]
            if missing_fields:
                raise Exception(f"❌ Medical bill extraction missing required fields: {missing_fields}")
            
            bill_data = {
                "patient_name": bill_extracted['patient_name'],
                "bill_date": bill_extracted['bill_date'],
                "bill_amount": float(bill_extracted['bill_amount'])
            }
            extracted_document["medical_bill_doc"] = bill_data
            self.logger.info(f"📄 Added medical_bill_doc: {bill_data}")
        
        if "memo_doc" in extracted_data:
            memo_extracted = extracted_data["memo_doc"]
            if isinstance(memo_extracted, dict) and "error" in memo_extracted:
                raise Exception(f"❌ Memo extraction failed: {memo_extracted['error']}")
            
            if not isinstance(memo_extracted, dict):
                raise Exception(f"❌ Memo extraction returned invalid data type: {type(memo_extracted)}")
            
            # Ensure required fields are present
            required_fields = ['patient_name', 'medical_condition']
            missing_fields = [field for field in required_fields if field not in memo_extracted]
            if missing_fields:
                raise Exception(f"❌ Memo extraction missing required fields: {missing_fields}")
            
            memo_data = {
                "patient_name": memo_extracted['patient_name'],
                "medical_condition": memo_extracted['medical_condition']
            }
            extracted_document["memo_doc"] = memo_data
            self.logger.info(f"📄 Added memo_doc: {memo_data}")
        
        # For inpatient claims, add discharge summary if available
        if "discharge_summary_doc" in extracted_data:
            # Use extracted patient_name as primary source, claim_info as fallback
            extracted_patient_name = extracted_data["discharge_summary_doc"].get("patient_name", "")
            fallback_patient_name = claim_info.get('patient_name', 'Unknown')
            final_patient_name = extracted_patient_name if extracted_patient_name else fallback_patient_name
            
            discharge_data = {
                "patient_name": final_patient_name,
                "hospital_name": extracted_data["discharge_summary_doc"].get("hospital_name", "Unknown Hospital"),
                "admit_date": extracted_data["discharge_summary_doc"].get("admit_date", "Unknown"),
                "discharge_date": extracted_data["discharge_summary_doc"].get("discharge_date", "Unknown"),
                "medical_condition": claim_info.get('diagnosis', 'Unknown condition')
            }
            extracted_document["discharge_summary_doc"] = discharge_data
            self.logger.info(f"📄 Added discharge_summary_doc with corrected patient_name: {discharge_data}")
            self.logger.info(f"🔍 Patient name sources - Extracted: '{extracted_patient_name}', Claim info: '{fallback_patient_name}', Final: '{final_patient_name}'")
        
        self.logger.info(f"📄 FINAL DOCUMENT TO WRITE: {extracted_document}")
        
        try:
            container = self.cosmos_database.get_container_client("extracted_patient_data")
            result = container.upsert_item(extracted_document)
            self.logger.info(f"✅ Successfully wrote document to Cosmos DB")
            self.logger.info(f"✅ Cosmos DB response: {result}")
        except Exception as e:
            self.logger.error(f"❌ Failed to write to Cosmos DB: {str(e)}")
            raise Exception(f"Failed to write extracted data to Cosmos DB: {str(e)}")
        
        self.logger.info(f"✅ Successfully wrote extracted data for {claim_id} to Cosmos DB extracted_patient_data container")
        self.logger.info(f"📄 Document structure: {list(extracted_document.keys())}")
    
    async def _process_documents_with_azure_di(self, urls: List[str], claim_info: Dict[str, Any]) -> Dict[str, Any]:
        """Process documents with Azure Document Intelligence"""
        self.logger.info(f"🔄 Processing {len(urls)} documents with Azure DI")
        extracted_data = {}
        
        for i, url in enumerate(urls, 1):
            self.logger.info(f"📄 Processing document {i}/{len(urls)}: {url}")
            doc_type = self._determine_document_type(url)
            self.logger.info(f"🏷️ Detected document type: {doc_type}")
            
            try:
                data = await self._extract_from_document(url, doc_type)
                self.logger.info(f"✅ Successfully extracted data from {doc_type}: {data}")
                if data:
                    extracted_data[doc_type] = data
                else:
                    self.logger.warning(f"⚠️ No data extracted from {doc_type}")
            except Exception as e:
                self.logger.error(f"❌ Failed to extract data from {doc_type} at {url}: {str(e)}")
                # Continue with other documents even if one fails
        
        self.logger.info(f"📊 Final extracted data summary: {list(extracted_data.keys())}")
        return extracted_data
    
    def _determine_document_type(self, url: str) -> str:
        """Determine document type from URL"""
        url_lower = url.lower()
        if 'discharge' in url_lower:
            return 'discharge_summary_doc'
        elif 'bill' in url_lower:
            return 'medical_bill_doc'
        elif 'memo' in url_lower:
            return 'memo_doc'
        return 'unknown_doc'
    
    async def _extract_from_document(self, url: str, doc_type: str) -> Dict[str, Any]:
        """Extract data from document using Azure Document Intelligence - NO SIMULATION"""
        if not self.document_intelligence_client:
            raise Exception(f"❌ Azure Document Intelligence client not initialized. Cannot process {doc_type} from {url}. Check environment variables: AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT, AZURE_DOCUMENT_INTELLIGENCE_KEY")
        
        self.logger.info(f"🔍 Starting Azure DI extraction for {doc_type} from URL: {url}")
        
        try:
            # Try different API formats based on SDK version
            self.logger.info(f"🔧 Attempting Azure DI API call for {doc_type}...")
            
            try:
                # First attempt: newer SDK format with AnalyzeDocumentRequest
                from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
                analyze_request = AnalyzeDocumentRequest(url_source=url)
                poller = self.document_intelligence_client.begin_analyze_document(
                    model_id="prebuilt-read",
                    analyze_request=analyze_request
                )
                self.logger.info(f"✅ Using AnalyzeDocumentRequest format for {doc_type}")
                
            except Exception as e1:
                self.logger.info(f"⚠️ AnalyzeDocumentRequest failed: {e1}")
                try:
                    # Second attempt: direct body parameter
                    poller = self.document_intelligence_client.begin_analyze_document(
                        model_id="prebuilt-read",
                        body={"urlSource": url}
                    )
                    self.logger.info(f"✅ Using body parameter format for {doc_type}")
                    
                except Exception as e2:
                    self.logger.info(f"⚠️ Body parameter failed: {e2}")
                    # Third attempt: analyze_request parameter with dict
                    poller = self.document_intelligence_client.begin_analyze_document(
                        "prebuilt-read",  # model_id as positional argument
                        {"urlSource": url}    # body as positional argument
                    )
                    self.logger.info(f"✅ Using positional arguments format for {doc_type}")
            
            # Wait for the operation to complete
            self.logger.info(f"⏳ Waiting for Azure DI analysis to complete for {doc_type}...")
            result = poller.result()
            self.logger.info(f"✅ Azure DI analysis completed for {doc_type}")
            
            # Extract data based on document type
            extracted_data = self._parse_azure_di_result(result, doc_type)
            
            self.logger.info(f"✅ Successfully extracted data from {doc_type}: {extracted_data}")
            return extracted_data
            
        except Exception as e:
            self.logger.error(f"❌ Azure DI API error for {doc_type}: {e}")
            self.logger.error(f"❌ All API format attempts failed for {doc_type}")
            raise e
    
    def _parse_azure_di_result(self, result, doc_type: str) -> Dict[str, Any]:
        """Parse Azure Document Intelligence result using LLM for smart extraction"""
        self.logger.info(f"🔍 Parsing Azure DI result for {doc_type}")
        
        # Get all the extracted text content
        content = ""
        if hasattr(result, 'content') and result.content:
            content = result.content
            self.logger.info(f"📝 Extracted text content length: {len(content)} characters")
            self.logger.info(f"📝 First 500 chars of content: {content[:500]}...")
        else:
            self.logger.warning(f"⚠️ No text content found in Azure DI result")
        
        # Extract key-value pairs from the document
        key_value_pairs = {}
        if hasattr(result, 'key_value_pairs') and result.key_value_pairs:
            self.logger.info(f"📊 Found {len(result.key_value_pairs)} key-value pairs")
            for kv_pair in result.key_value_pairs:
                if kv_pair.key and kv_pair.value:
                    key = kv_pair.key.content.strip()
                    value = kv_pair.value.content.strip()
                    key_value_pairs[key] = value
                    self.logger.info(f"📋 Key-Value: '{key}' = '{value}'")
        else:
            self.logger.warning(f"⚠️ No key-value pairs found in Azure DI result")
        
        self.logger.info(f"📊 Total extracted key-value pairs: {len(key_value_pairs)}")
        
        # Use LLM for intelligent data extraction
        self.logger.info(f"🧠 Using LLM for intelligent data extraction from {doc_type}")
        extracted_data = self._extract_with_llm(content, key_value_pairs, doc_type)
        self.logger.info(f"🧠 LLM extraction result: {extracted_data}")
        
        return extracted_data
    
    def _extract_with_llm(self, content: str, kv_pairs: Dict[str, str], doc_type: str) -> Dict[str, Any]:
        """Extract data using LLM for intelligent understanding"""
        self.logger.info(f"🧠 Starting LLM extraction for {doc_type}")
        self.logger.info(f"📊 Input data - Content length: {len(content)}, KV pairs: {len(kv_pairs)}")
        
        try:
            # Import Azure OpenAI client
            from openai import AzureOpenAI
            
            # Initialize Azure OpenAI client
            client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            
            self.logger.info(f"✅ Azure OpenAI client initialized for LLM extraction")
            
            # Create extraction prompt based on document type
            extraction_prompt = self._create_extraction_prompt(content, kv_pairs, doc_type)
            self.logger.info(f"📝 Created extraction prompt for {doc_type}")
            
            # Call LLM for extraction
            self.logger.info(f"🧠 Calling LLM for data extraction...")
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
                messages=[
                    {"role": "system", "content": "You are a medical document data extraction expert."},
                    {"role": "user", "content": extraction_prompt}
                ],
                temperature=0.1
            )
            
            llm_response = response.choices[0].message.content
            self.logger.info(f"🧠 LLM raw response: {llm_response}")
            
            # Parse the LLM response (expecting JSON)
            try:
                import json
                # Clean markdown code blocks if present
                cleaned_response = llm_response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()
                elif cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response.replace("```", "").strip()
                
                extracted_data = json.loads(cleaned_response)
                self.logger.info(f"✅ Successfully parsed LLM JSON response: {extracted_data}")
                return extracted_data
            except json.JSONDecodeError as e:
                self.logger.error(f"❌ Failed to parse LLM response as JSON: {e}")
                self.logger.error(f"📝 Raw LLM response: {llm_response}")
                self.logger.error(f"📝 Cleaned response: {cleaned_response}")
                raise Exception(f"LLM extraction failed for {doc_type}: Unable to parse JSON response - {str(e)}")
                
        except Exception as e:
            self.logger.error(f"❌ LLM extraction failed for {doc_type}: {str(e)}")
            raise  # Re-raise the exception instead of returning error dict
            
            # Call LLM for extraction
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini-deployment"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert medical document analyst. Extract specific information from medical documents and return ONLY valid JSON. Be precise and only extract information that is clearly present in the document."
                    },
                    {
                        "role": "user",
                        "content": extraction_prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=500
            )
            
            # Parse LLM response
            llm_result = response.choices[0].message.content.strip()
            
            # Clean and parse JSON response
            if llm_result.startswith("```json"):
                llm_result = llm_result.replace("```json", "").replace("```", "").strip()
            
            extracted_data = json.loads(llm_result)
            
            self.logger.info(f"✅ LLM extraction successful for {doc_type}")
            return extracted_data
            
        except ImportError:
            raise Exception("❌ Azure OpenAI package not available. Install with: pip install openai")
        except Exception as e:
            self.logger.error(f"❌ LLM extraction failed for {doc_type}: {e}")
            raise Exception(f"Document extraction failed: {str(e)}")
    
    def _create_extraction_prompt(self, content: str, kv_pairs: Dict[str, str], doc_type: str) -> str:
        """Create intelligent extraction prompt based on document type"""
        
        # Base context
        kv_text = "\n".join([f"- {k}: {v}" for k, v in kv_pairs.items()]) if kv_pairs else "None found"
        
        if doc_type == 'discharge_summary_doc':
            return f"""
Extract the following information from this hospital discharge summary:

DOCUMENT CONTENT:
{content}

KEY-VALUE PAIRS FOUND:
{kv_text}

Extract these fields and return as JSON:
{{
    "patient_name": "Full patient name",
    "hospital_name": "Hospital or medical facility name", 
    "admit_date": "Admission date in YYYY-MM-DD format",
    "discharge_date": "Discharge date in YYYY-MM-DD format",
    "medical_condition": "Primary diagnosis or medical condition"
}}

Rules:
- Only include fields where you can find clear information
- Use YYYY-MM-DD format for dates
- If a field is not found, omit it from the JSON
- Return ONLY the JSON object, no explanations
"""

        elif doc_type == 'medical_bill_doc':
            return f"""
Extract the following information from this medical bill:

DOCUMENT CONTENT:
{content}

KEY-VALUE PAIRS FOUND:
{kv_text}

Extract these fields and return as JSON:
{{
    "patient_name": "Full patient name",
    "bill_date": "Bill or service date in YYYY-MM-DD format", 
    "bill_amount": 123.45
}}

Rules:
- Only include fields where you can find clear information
- Use YYYY-MM-DD format for dates
- Return bill_amount as a number (not string)
- If a field is not found, omit it from the JSON
- Return ONLY the JSON object, no explanations
"""

        elif doc_type == 'memo_doc':
            return f"""
Extract the following information from this medical memo/note:

DOCUMENT CONTENT:
{content}

KEY-VALUE PAIRS FOUND:
{kv_text}

Extract these fields and return as JSON:
{{
    "patient_name": "Full patient name",
    "medical_condition": "Medical condition or diagnosis mentioned"
}}

Rules:
- Only include fields where you can find clear information
- If a field is not found, omit it from the JSON
- Return ONLY the JSON object, no explanations
"""

        else:
            return f"""
Extract any relevant medical information from this document:

DOCUMENT CONTENT:
{content}

KEY-VALUE PAIRS FOUND:
{kv_text}

Return any found information as JSON with appropriate field names.
"""

    async def _call_intake_clarifier(self, claim_id: str) -> Dict[str, Any]:
        """
        Call intake clarifier to verify extracted data against original claim data
        Returns: {"status": "success"|"error", "message": "description"}
        """
        try:
            self.logger.info(f"📋 Calling intake clarifier for claim {claim_id}")
            
            # Prepare task for intake clarifier
            intake_task = f"""Compare claim data with extracted patient data:
Claim ID: {claim_id}

Fetch documents from:
- claim_details container (claim_id: {claim_id})  
- extracted_patient_data container (claim_id: {claim_id})

Compare: patient_name, bill_amount, bill_date, diagnosis vs medical_condition
If mismatch: Update status to 'marked for rejection' with reason
If match: Update status to 'marked for approval'"""
            
            # Call intake clarifier via A2A
            intake_result = await self.a2a_client.send_request(
                target_agent="intake_clarifier",
                task=intake_task,
                parameters={"claim_id": claim_id}
            )
            
            # Process the result
            if intake_result:
                # Check if it's a successful approval
                result_str = str(intake_result).lower()
                if "approved" in result_str or "marked for approval" in result_str:
                    self.logger.info(f"✅ Intake clarifier approved claim {claim_id}")
                    return {
                        "status": "success",
                        "message": "Claim approved and status updated"
                    }
                elif "rejected" in result_str or "marked for rejection" in result_str:
                    self.logger.info(f"❌ Intake clarifier rejected claim {claim_id}")
                    return {
                        "status": "error", 
                        "message": "Claim rejected due to data mismatch"
                    }
                else:
                    self.logger.warning(f"⚠️ Unclear result from intake clarifier for {claim_id}")
                    return {
                        "status": "error",
                        "message": f"Unclear verification result: {intake_result}"
                    }
            else:
                self.logger.error(f"❌ No response from intake clarifier for {claim_id}")
                return {
                    "status": "error",
                    "message": "No response from intake clarifier"
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error calling intake clarifier for {claim_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to call intake clarifier: {str(e)}"
            }

print("📄 Document Intelligence Executor loaded successfully!")
print("✅ Updated implementation with direct Cosmos DB access and orchestrator-provided URLs")
