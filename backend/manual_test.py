#!/usr/bin/env python3
"""
Manual Interactive Test

This allows you to have a full conversation with the struggling student
and consult the mentor whenever you want.

Usage: python backend/manual_test.py
"""

import sys
import os

# Add parent directory to path so we can import backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.conversation_manager import ConversationManager


def print_header():
    """Print a nice header"""
    print("\n" + "=" * 70)
    print(" " * 15 + "🎓 EDUCATIONAL CHATBOT - MANUAL TEST 🎓")
    print("=" * 70)
    print("\n📖 INSTRUCTIONS:")
    print("  • You are the student-teacher")
    print("  • Try to explain Newton's First Law to the struggling student")
    print("  • Type your explanation and press Enter")
    print("  • Type 'mentor' to get coaching advice")
    print("  • Type 'summary' to see conversation stats")
    print("  • Type 'quit' to exit")
    print("\n" + "=" * 70 + "\n")


def print_divider():
    """Print a visual divider"""
    print("\n" + "-" * 70 + "\n")


def main():
    """Run interactive test"""
    print_header()
    
    # Initialize conversation manager
    try:
        manager = ConversationManager()
        print("✅ Conversation manager initialized\n")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        print("\nMake sure you have:")
        print("  1. Created a .env file with your OPENAI_API_KEY")
        print("  2. Installed dependencies: pip install -r requirements.txt")
        return
    
    # Start conversation
    try:
        initial_message = manager.start_conversation()
    except Exception as e:
        print(f"❌ Failed to start conversation: {e}")
        return
    
    print("🧑 STRUGGLING STUDENT:")
    print(f"   {initial_message}")
    print_divider()
    
    # Conversation loop
    turn = 0
    while True:
        # Get input
        try:
            teacher_input = input("👨‍🏫 YOU: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting...\n")
            break
        
        # Handle empty input
        if not teacher_input:
            continue
        
        # Handle commands
        command = teacher_input.lower()
        
        if command == 'quit':
            print("\n👋 Goodbye!\n")
            break
        
        if command == 'summary':
            summary = manager.get_conversation_summary()
            print("\n📊 CONVERSATION SUMMARY:")
            print(f"   • Total turns: {summary['turns']}")
            print(f"   • Your explanations: {summary['student_messages']}")
            print(f"   • Mentor consultations: {summary['mentor_consultations']}")
            print()
            continue
        
        if command == 'mentor':
            # Get context
            last_student_msg = manager.get_last_student_message()
            
            # Get last teacher message
            history = manager.get_student_history()
            last_teacher_msg = ""
            if history:
                for msg in reversed(history):
                    if msg["role"] == "user":
                        last_teacher_msg = msg["content"]
                        break
            
            if not last_teacher_msg:
                print("\n⚠️  You haven't sent a message yet. Try explaining first!\n")
                continue
            
            # Get mentor advice
            print("\n💭 Consulting mentor...\n")
            try:
                advice = manager.consult_mentor(last_teacher_msg, last_student_msg)
                print("🎓 MENTOR COACH:")
                print(f"   {advice}")
                print_divider()
            except Exception as e:
                print(f"❌ Mentor consultation failed: {e}\n")
            
            continue
        
        # Send to student
        print("\n🤔 Student is thinking...\n")
        try:
            student_response = manager.send_to_student(teacher_input)
            turn += 1
            
            print("🧑 STRUGGLING STUDENT:")
            print(f"   {student_response}")
            print_divider()
            
        except Exception as e:
            print(f"❌ Error: {e}\n")
            print("This might be an API issue. Check your connection and API key.\n")
    
    # Final summary
    if turn > 0:
        summary = manager.get_conversation_summary()
        print("\n" + "=" * 70)
        print("📊 FINAL SUMMARY")
        print("=" * 70)
        print(f"Total conversation turns: {summary['turns']}")
        print(f"Your explanations sent: {summary['student_messages']}")
        print(f"Times you consulted mentor: {summary['mentor_consultations']}")
        print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
