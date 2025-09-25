"""Communication Agent Executor

Handles email notifications for insurance claim results using Azure Communication Services.
"""

import os
import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

# Azure Communication Services imports
try:
    from azure.communication.email import EmailClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from shared.base_agent import BaseInsuranceAgent

class CommunicationAgentExecutor(BaseInsuranceAgent):
    """Communication Agent for sending email notifications about claim results"""
    
    def __init__(self):
        super().__init__(
            agent_name="communication_agent",
            agent_description="Sends email notifications for insurance claim decisions using Azure Communication Services",
            port=8005
        )
        self.capabilities = [
            "send_claim_notification",
            "send_email",
            "format_claim_email"
        ]
        
        # Email configuration
        self.recipient_email = "abc@abc.com"
        self.sender_email = None  # Will be set from Azure config
        self.email_client = None
        
        # Initialize Azure Communication Services
        self._initialize_azure_communication()
    
    def _initialize_azure_communication(self):
        """Initialize Azure Communication Services client"""
        if not AZURE_AVAILABLE:
            self.logger.error("Azure Communication Services SDK not installed")
            return
            
        try:
            # Get connection string from environment
            connection_string = os.getenv('AZURE_COMMUNICATION_CONNECTION_STRING')
            if not connection_string:
                self.logger.warning("AZURE_COMMUNICATION_CONNECTION_STRING not found in environment")
                return
                
            self.email_client = EmailClient.from_connection_string(connection_string)
            self.sender_email = os.getenv('AZURE_COMMUNICATION_SENDER_EMAIL', 'noreply@yourdomain.com')
            self.logger.info("Azure Communication Services initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Azure Communication Services: {e}")
    
    async def process_request(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming requests"""
        try:
            if action == "send_claim_notification":
                return await self._send_claim_notification(data)
            elif action == "health_check":
                return await self._health_check()
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            self.log_error(f"Error processing request: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def _health_check(self) -> Dict[str, Any]:
        """Check if the agent is healthy and ready to send emails"""
        is_healthy = (
            AZURE_AVAILABLE and 
            self.email_client is not None and 
            self.sender_email is not None
        )
        
        return {
            "success": True,
            "healthy": is_healthy,
            "azure_available": AZURE_AVAILABLE,
            "client_initialized": self.email_client is not None,
            "sender_configured": self.sender_email is not None,
            "timestamp": datetime.now().isoformat()
        }
    
    async def _send_claim_notification(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send email notification about claim result"""
        try:
            # Validate input data
            if not data:
                return {
                    "success": False,
                    "error": "No data provided for email notification",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Check if email service is available
            if not self.email_client:
                return {
                    "success": False,
                    "error": "Azure Communication Services not properly configured",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Format email content
            email_content = self._format_claim_email(data)
            
            # Create email message using the correct Azure Communication Services format
            email_message = {
                "senderAddress": self.sender_email,
                "recipients": {
                    "to": [{"address": self.recipient_email}]
                },
                "content": {
                    "subject": email_content["subject"],
                    "plainText": email_content["text_body"],
                    "html": email_content["html_body"]
                }
            }
            
            # Send email
            response = await self._send_email_async(email_message)
            
            # Prepare result
            result = None
            if response["success"]:
                self.logger.info(f"Email notification sent successfully to {self.recipient_email}")
                result = {
                    "success": True,
                    "message": f"Email notification sent to {self.recipient_email}",
                    "message_id": response.get("message_id"),
                    "timestamp": datetime.now().isoformat()
                }
                
                # Send notification to dashboard
                await self._notify_dashboard("sent", data, result)
                
            else:
                self.logger.error(f"Failed to send email: {response.get('error')}")
                result = {
                    "success": False,
                    "error": f"Email sending failed: {response.get('error')}",
                    "timestamp": datetime.now().isoformat()
                }
                
                # Send failure notification to dashboard
                await self._notify_dashboard("failed", data, result)
            
            return result
                
        except Exception as e:
            self.logger.error(f"Error sending claim notification: {e}")
            return {
                "success": False,
                "error": f"Email notification failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _format_claim_email(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Format the claim result data into email content"""
        try:
            # Extract key information from the data
            claim_id = data.get("claim_id", "N/A")
            claim_status = data.get("status", "Unknown")
            claim_amount = data.get("amount", "N/A")
            decision_reason = data.get("reason", "No reason provided")
            timestamp = data.get("timestamp", datetime.now().isoformat())
            
            # Determine if claim was approved or denied
            is_approved = claim_status.lower() in ["approved", "accepted", "claim accepted"]
            
            # Create subject
            subject = f"Insurance Claim {claim_id} - {'Approved' if is_approved else 'Update'}"
            
            # Create HTML email body
            html_body = f"""
            <html>
            <body>
                <h2>Insurance Claim Notification</h2>
                <p>Dear Policyholder,</p>
                
                <p>We are writing to inform you about the status of your insurance claim.</p>
                
                <div style="background-color: #f5f5f5; padding: 15px; margin: 20px 0; border-left: 4px solid {'#28a745' if is_approved else '#dc3545'};">
                    <h3>Claim Details:</h3>
                    <ul>
                        <li><strong>Claim ID:</strong> {claim_id}</li>
                        <li><strong>Status:</strong> {claim_status}</li>
                        <li><strong>Amount:</strong> {claim_amount}</li>
                        <li><strong>Decision Date:</strong> {timestamp}</li>
                    </ul>
                </div>
                
                <div style="margin: 20px 0;">
                    <h3>Decision Details:</h3>
                    <p>{decision_reason}</p>
                </div>
                
                <p>If you have any questions about this decision, please contact our customer service team.</p>
                
                <p>Thank you for choosing our insurance services.</p>
                
                <p>Best regards,<br>
                Insurance Claims Department</p>
            </body>
            </html>
            """
            
            # Create plain text email body
            text_body = f"""
Insurance Claim Notification

Dear Policyholder,

We are writing to inform you about the status of your insurance claim.

Claim Details:
- Claim ID: {claim_id}
- Status: {claim_status}
- Amount: {claim_amount}
- Decision Date: {timestamp}

Decision Details:
{decision_reason}

If you have any questions about this decision, please contact our customer service team.

Thank you for choosing our insurance services.

Best regards,
Insurance Claims Department
            """
            
            return {
                "subject": subject,
                "html_body": html_body,
                "text_body": text_body
            }
            
        except Exception as e:
            self.logger.error(f"Error formatting email: {e}")
            return {
                "subject": "Insurance Claim Notification",
                "html_body": f"<p>Claim notification: {json.dumps(data, indent=2)}</p>",
                "text_body": f"Claim notification: {json.dumps(data, indent=2)}"
            }
    
    async def _send_email_async(self, email_message: Dict[str, Any]) -> Dict[str, Any]:
        """Send email asynchronously using Azure Communication Services"""
        try:
            # Send the email using the begin_send method
            poller = self.email_client.begin_send(email_message)
            result = poller.result()
            
            return {
                "success": True,
                "message_id": result.id if hasattr(result, 'id') else "unknown",
                "status": "sent"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _notify_dashboard(self, email_status: str, claim_data: Dict[str, Any], email_result: Dict[str, Any]):
        """Send notification to the dashboard about email status"""
        try:
            import httpx
            
            dashboard_url = "http://localhost:3000/api/email-notification"
            
            notification_data = {
                "claim_id": claim_data.get("claim_id", "Unknown"),
                "email_status": email_status,
                "details": {
                    "recipient": self.recipient_email,
                    "sender": self.sender_email,
                    "claim_data": claim_data,
                    "email_result": email_result,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(dashboard_url, json=notification_data)
                
                if response.status_code == 200:
                    self.logger.info(f"📢 Dashboard notification sent: {email_status} for claim {claim_data.get('claim_id')}")
                else:
                    self.logger.warning(f"📢 Dashboard notification failed: {response.status_code}")
                    
        except Exception as e:
            # Don't fail email sending if dashboard notification fails
            self.logger.warning(f"📢 Failed to notify dashboard: {e}")
    
    def get_available_actions(self) -> list:
        """Return list of available actions"""
        return [
            {
                "action": "send_claim_notification",
                "description": "Send email notification about claim result",
                "parameters": {
                    "claim_id": "string",
                    "status": "string", 
                    "amount": "string",
                    "reason": "string",
                    "timestamp": "string (optional)"
                }
            },
            {
                "action": "health_check",
                "description": "Check if the email service is available and configured",
                "parameters": {}
            }
        ]