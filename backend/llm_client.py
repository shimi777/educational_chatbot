#!/usr/bin/env python3
"""
LLM Client - Abstraction layer for OpenAI/Ollama
This allows easy switching between cloud and local models
"""

import os
from typing import List, Dict
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class LLMClient:
    """
    Unified interface for LLM calls.
    Supports both OpenAI API and Ollama (local).
    """
    
    def __init__(self, use_ollama: bool = False):
        """
        Initialize LLM client
        
        Args:
            use_ollama: If True, use Ollama. Otherwise use OpenAI.
        """
        self.use_ollama = use_ollama or os.getenv('USE_OLLAMA', 'false').lower() == 'true'
        
        if self.use_ollama:
            self._init_ollama()
        else:
            self._init_openai()
    
    def _init_openai(self):
        """Initialize OpenAI client"""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        
        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv('MODEL_NAME', 'gpt-4o-mini')
        print(f"✅ Using OpenAI model: {self.model}")
    
    def _init_ollama(self):
        """Initialize Ollama client"""
        # Ollama runs locally on http://localhost:11434
        self.client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"  # Ollama doesn't need real API key
        )
        self.model = os.getenv('OLLAMA_MODEL', 'llama3.1:8b')
        print(f"✅ Using Ollama model: {self.model}")
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> str:
        """
        Send chat messages to LLM and get response
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Randomness (0=deterministic, 1=creative)
            max_tokens: Maximum response length
        
        Returns:
            Response text from the model
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"❌ Error calling LLM: {e}")
            raise
    
    def get_usage_stats(self, response) -> Dict:
        """
        Extract usage statistics from response
        (Only works for OpenAI, not Ollama)
        """
        if self.use_ollama:
            return {"note": "Usage stats not available for Ollama"}
        
        try:
            return {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "estimated_cost": response.usage.total_tokens * 0.00000015  # gpt-4o-mini pricing
            }
        except:
            return {}


# Quick test function
def test_client():
    """Test the LLM client with a simple message"""
    print("Testing LLM Client...")
    
    client = LLMClient()
    
    messages = [
        {"role": "system", "content": "You are a helpful math tutor."},
        {"role": "user", "content": "Explain what 2+2 equals in one sentence."}
    ]
    
    response = client.chat(messages, temperature=0.5, max_tokens=100)
    print(f"\n📝 Response: {response}\n")


if __name__ == "__main__":
    test_client()
