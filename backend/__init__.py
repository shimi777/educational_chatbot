"""
Educational Chatbot Backend

Main components:
- LLMClient: Handles OpenAI/Ollama API calls
- ConversationManager: Manages dual-agent conversations
- Prompts: All prompt templates in one place
"""

from .llm_client import LLMClient
from .conversation_manager import ConversationManager

__all__ = ['LLMClient', 'ConversationManager']
