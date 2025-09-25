"""Communication Agent Package

This agent handles email notifications for insurance claim results using Azure Communication Services.
It acts as an optional external agent that sends email notifications after claim processing is complete.
"""

from .communication_agent_executor import CommunicationAgentExecutor

__all__ = ['CommunicationAgentExecutor']