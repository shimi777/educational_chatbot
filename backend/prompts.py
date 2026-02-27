#!/usr/bin/env python3
"""
Prompt Templates for Educational Chatbot — Generic Version

All prompts are now driven by TopicConfig (generated dynamically).
This file provides helper functions that format messages for the LLM,
reading content from TopicConfig instead of hardcoded constants.
"""

from backend.topic_config import TopicConfig
from backend.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# LANGUAGE CONFIGURATION
# ============================================================================

LANGUAGE_INSTRUCTION = {
    "en": "You MUST respond in English only.",
    "he": "You MUST respond in Hebrew (עברית) only. Use Hebrew script for your entire response."
}


# ============================================================================
# PROMPT ACCESSORS (read from TopicConfig)
# ============================================================================

def get_prompts_for_language(lang: str, topic_config: TopicConfig) -> dict:
    """
    Get all prompt strings for the specified language from the TopicConfig.

    Args:
        lang: "en" for English, "he" for Hebrew
        topic_config: The generated topic configuration

    Returns:
        Dictionary with all prompt strings for that language
    """
    return {
        "student_system": topic_config.get_student_persona(lang),
        "student_initial": topic_config.get_student_initial_message(lang),
        "mentor_system": topic_config.get_mentor_prompt(lang),
        "evaluation_prompt": topic_config.get_evaluation_prompt(lang),
        "lang_instruction": LANGUAGE_INSTRUCTION.get(lang, LANGUAGE_INSTRUCTION["en"]),
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_struggling_student_messages(
    conversation_history: list = None,
    lang: str = "en",
    topic_config: TopicConfig = None,
) -> list:
    """
    Get messages formatted for the struggling student agent.

    Args:
        conversation_history: List of previous messages
        lang: "en" or "he"
        topic_config: The generated topic configuration

    Returns:
        List of message dicts ready for LLM
    """
    prompts = get_prompts_for_language(lang, topic_config)
    system_content = prompts["student_system"] + "\n\n" + prompts["lang_instruction"]

    messages = [
        {"role": "system", "content": system_content}
    ]

    if conversation_history:
        messages.extend(conversation_history)
    else:
        messages.append({
            "role": "assistant",
            "content": prompts["student_initial"]
        })

    return messages


def get_mentor_messages(
    explanation: str,
    context: str = "",
    lang: str = "en",
    topic_config: TopicConfig = None,
) -> list:
    """
    Get messages formatted for the mentor agent.

    Args:
        explanation: The student-teacher's explanation to analyze
        context: Optional context about what the struggling student said
        lang: "en" or "he"
        topic_config: The generated topic configuration

    Returns:
        List of message dicts ready for LLM
    """
    prompts = get_prompts_for_language(lang, topic_config)
    system_content = prompts["mentor_system"] + "\n\n" + prompts["lang_instruction"]

    messages = [
        {"role": "system", "content": system_content}
    ]

    if lang == "he":
        if context:
            user_message = f"""התלמיד המתקשה אמר: "{context}"

מתרגל-ההוראה הגיב: "{explanation}"

אנא ספק משוב אימון קצר (2-3 משפטים) על איך הוא יכול לשפר את ההסבר."""
        else:
            user_message = f"""מתרגל-ההוראה נתן את ההסבר הבא: "{explanation}"

אנא ספק משוב אימון קצר (2-3 משפטים)."""
    else:
        if context:
            user_message = f"""The struggling student said: "{context}"

The student-teacher responded: "{explanation}"

Please provide brief coaching feedback (2-3 sentences) on how they can improve this explanation."""
        else:
            user_message = f"""The student-teacher gave this explanation: "{explanation}"

Please provide brief coaching feedback (2-3 sentences)."""

    messages.append({"role": "user", "content": user_message})
    return messages


def get_evaluation_messages(
    conversation_history: list,
    lang: str = "en",
    topic_config: TopicConfig = None,
) -> list:
    """
    Get messages for evaluating the full conversation.

    Args:
        conversation_history: The full student conversation history
        lang: "en" or "he"
        topic_config: The generated topic configuration

    Returns:
        List of message dicts ready for LLM
    """
    prompts = get_prompts_for_language(lang, topic_config)

    # Build conversation transcript
    transcript_lines = []
    for msg in conversation_history:
        if msg["role"] == "user":
            label = "מתרגל-הוראה" if lang == "he" else "Student-Teacher"
        else:
            label = "תלמיד מתקשה" if lang == "he" else "Struggling Student"
        transcript_lines.append(f"{label}: {msg['content']}")

    transcript = "\n\n".join(transcript_lines)
    separator = "===== שיחה מלאה =====" if lang == "he" else "===== FULL CONVERSATION ====="

    return [
        {"role": "system", "content": "You are an objective evaluator of teaching quality. " + prompts["lang_instruction"]},
        {"role": "user", "content": f"{prompts['evaluation_prompt']}\n\n{separator}\n\n{transcript}"}
    ]


# Quick test
if __name__ == "__main__":
    logger.info("Testing prompt templates (generic version)...")

    # Create a minimal test TopicConfig
    _config = TopicConfig(
        topic_name_en="Photosynthesis",
        student_persona_en="You are a confused 10-year-old learning about photosynthesis.",
        student_initial_message_en="Hi! I don't understand how plants make food from sunlight!",
        mentor_system_prompt_en="You are a teaching coach for photosynthesis explanations.",
        evaluation_prompt_en="Evaluate the explanation of photosynthesis.",
    )

    msgs = get_struggling_student_messages(lang="en", topic_config=_config)
    logger.info("Student messages: %d messages", len(msgs))
    logger.info("System prompt preview: %s...", msgs[0]["content"][:80])
    logger.info("Initial message: %s...", msgs[1]["content"][:80])

    mentor_msgs = get_mentor_messages(
        explanation="Plants use sunlight",
        context="How do plants eat?",
        lang="en",
        topic_config=_config,
    )
    logger.info("Mentor messages: %d messages", len(mentor_msgs))
    logger.info("Prompts OK (generic version)!")
