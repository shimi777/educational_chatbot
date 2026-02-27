#!/usr/bin/env python3
"""
Conversation Manager - The Brain of the Educational Chatbot

Manages dual-agent conversations:
1. Struggling Student Agent - the learner
2. Mentor Agent - coaches the student-teacher
3. Evaluation Agent - rates the student-teacher's performance

Now fully generic — all topic-specific content comes from TopicConfig.
"""

from typing import List, Dict, Optional
from backend.llm_client import LLMClient
from backend.topic_config import TopicConfig
from backend.logger import get_logger
from backend.prompts import (
    get_struggling_student_messages,
    get_mentor_messages,
    get_evaluation_messages,
    get_prompts_for_language,
)

logger = get_logger(__name__)


class ConversationManager:
    """
    Manages the dual conversation system:
    - Student-teacher <-> Struggling student
    - Student-teacher <-> Mentor (back-channel)
    - Evaluation of student-teacher performance

    All topic-specific content is provided via TopicConfig.
    """

    def __init__(self, use_ollama: bool = False, lang: str = "en",
                 topic_config: Optional[TopicConfig] = None):
        """
        Initialize the conversation manager.

        Args:
            use_ollama: Whether to use Ollama instead of OpenAI
            lang: Language code - "en" for English, "he" for Hebrew
            topic_config: Generated topic configuration (required for conversation)
        """
        self.llm = LLMClient(use_ollama=use_ollama)
        self.lang = lang
        self.topic_config = topic_config

        # Conversation histories
        self.student_history: List[Dict[str, str]] = []
        self.mentor_history: List[Dict[str, str]] = []

        # State
        self.is_initialized = False
        self.turn_count = 0

    def set_language(self, lang: str):
        """Change the language for future messages."""
        self.lang = lang

    def set_topic_config(self, topic_config: TopicConfig):
        """Set or update the topic configuration."""
        self.topic_config = topic_config

    def start_conversation(self) -> str:
        """
        Start a new conversation with the struggling student.

        Returns:
            Initial message from the struggling student

        Raises:
            ValueError: If no topic_config is set
        """
        if not self.topic_config:
            raise ValueError("No TopicConfig set. Generate or load a topic first.")

        # Reset state
        self.student_history = []
        self.mentor_history = []
        self.turn_count = 0
        self.is_initialized = True

        logger.info(
            "Conversation started | topic='%s' | lang=%s",
            self.topic_config.topic_name_en,
            self.lang,
        )

        # Return initial student message in the current language
        prompts = get_prompts_for_language(self.lang, self.topic_config)
        return prompts["student_initial"]

    def send_to_student(self, teacher_message: str) -> str:
        """
        Send a message to the struggling student and get response.

        Args:
            teacher_message: What the student-teacher says

        Returns:
            Response from the struggling student
        """
        if not self.is_initialized:
            raise ValueError("Conversation not started. Call start_conversation() first.")

        # Add teacher's message to history
        self.student_history.append({
            "role": "user",
            "content": teacher_message
        })

        # Get messages for LLM
        messages = get_struggling_student_messages(
            self.student_history,
            lang=self.lang,
            topic_config=self.topic_config
        )

        # Get student's response
        student_response = self.llm.chat(
            messages=messages,
            temperature=0.7,
            max_tokens=300
        )

        # Add student's response to history
        self.student_history.append({
            "role": "assistant",
            "content": student_response
        })

        self.turn_count += 1
        logger.debug("Turn %d completed", self.turn_count)
        return student_response

    def consult_mentor(self, teacher_explanation: str, student_context: str = "") -> str:
        """
        Get coaching advice from the mentor agent.

        Args:
            teacher_explanation: What the student-teacher just said
            student_context: What the struggling student said (for context)

        Returns:
            Coaching advice from the mentor
        """
        messages = get_mentor_messages(
            explanation=teacher_explanation,
            context=student_context,
            lang=self.lang,
            topic_config=self.topic_config
        )

        mentor_response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=200
        )

        self.mentor_history.append({
            "explanation": teacher_explanation,
            "advice": mentor_response,
            "turn": self.turn_count,
        })

        logger.debug("Mentor consultation #%d completed", len(self.mentor_history))
        return mentor_response

    def evaluate_performance(self) -> str:
        """
        Evaluate the student-teacher's overall performance.

        Returns:
            Evaluation text with scores and feedback
        """
        if not self.student_history:
            if self.lang == "he":
                return "אין שיחה להערכה. שלח לפחות הודעה אחת לתלמיד."
            return "No conversation to evaluate. Send at least one message to the student."

        messages = get_evaluation_messages(
            self.student_history,
            lang=self.lang,
            topic_config=self.topic_config
        )

        evaluation = self.llm.chat(
            messages=messages,
            temperature=0.3,
            max_tokens=500,
        )

        logger.info(
            "Evaluation complete | turns=%d | mentor_consultations=%d",
            self.turn_count,
            len(self.mentor_history),
        )
        return evaluation

    def get_conversation_summary(self) -> Dict:
        """Get summary of the conversation so far."""
        return {
            "turns": self.turn_count,
            "student_messages": len([m for m in self.student_history if m["role"] == "user"]),
            "mentor_consultations": len(self.mentor_history),
            "is_active": self.is_initialized
        }

    def get_student_history(self) -> List[Dict[str, str]]:
        """Get the conversation history with the student."""
        return self.student_history.copy()

    def get_mentor_history(self) -> List[Dict]:
        """Get the history of mentor consultations."""
        return self.mentor_history.copy()

    def get_last_student_message(self) -> str:
        """Get the most recent message from the struggling student."""
        if not self.student_history:
            return ""
        for msg in reversed(self.student_history):
            if msg["role"] == "assistant":
                return msg["content"]
        return ""
