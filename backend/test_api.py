#!/usr/bin/env python3
"""
Quick test to verify OpenAI API connection works.
Run this first to make sure your setup is correct.

Usage: python backend/test_api.py
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

def test_openai_connection():
    """Test basic OpenAI API connection"""
    
    # Get API key
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY not found in .env file")
        print("Please create a .env file with your API key")
        return False
    
    if api_key == "sk-proj-your-key-here":
        print("❌ ERROR: Please replace the example API key with your real key")
        return False
    
    print("✅ API key found")
    
    # Initialize client
    try:
        client = OpenAI(api_key=api_key)
        print("✅ OpenAI client initialized")
    except Exception as e:
        print(f"❌ Failed to initialize OpenAI client: {e}")
        return False
    
    # Test API call
    print("\n🔄 Testing API call...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Cheap and fast for testing
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello! API is working!' in one sentence."}
            ],
            max_tokens=50,
            temperature=0.7
        )
        
        result = response.choices[0].message.content
        print(f"✅ API Response: {result}")
        print(f"\n📊 Tokens used: {response.usage.total_tokens}")
        print(f"💰 Estimated cost: ${response.usage.total_tokens * 0.00000015:.6f}")
        
        return True
        
    except Exception as e:
        print(f"❌ API call failed: {e}")
        return False

def main():
    print("=" * 60)
    print("Educational Chatbot - API Connection Test")
    print("=" * 60)
    
    success = test_openai_connection()
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 SUCCESS! Your setup is ready.")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Run: python backend/manual_test.py")
        print("2. Start building the conversation manager")
    else:
        print("\n" + "=" * 60)
        print("⚠️  Setup incomplete - fix the errors above")
        print("=" * 60)

if __name__ == "__main__":
    main()
