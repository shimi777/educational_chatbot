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
    "he": (
        "You MUST respond in Hebrew (עברית) only. Use Hebrew script for your entire response.\n"
        "Hebrew quality rules:\n"
        "- Write clear, fluent Hebrew — short sentences, natural word order.\n"
        "- Do NOT transliterate English words into Hebrew letters. Use the accepted Hebrew term, "
        "or keep the English word in Latin characters with parentheses.\n"
        "- Avoid awkward literal translations from English.\n"
        "- Do NOT use profanity, slang, or offensive language under any circumstances.\n"
        "- Your tone should be warm, respectful, and age-appropriate."
    ),
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


def get_single_explanation_evaluation_messages(
    explanation: str,
    evaluation_spec: dict,
    lang: str = "en",
    topic_config: TopicConfig = None,
) -> list:
    """
    Build strict JSON-scoring prompts for evaluating one explanation.

    Args:
        explanation: The explanation text to score.
        evaluation_spec: Dict with components/performance levels/instructions.
        lang: "en" or "he"
        topic_config: Optional topic config for topic naming context.

    Returns:
        List of message dicts ready for LLM.
    """
    lang_instruction = LANGUAGE_INSTRUCTION.get(lang, LANGUAGE_INSTRUCTION["en"])
    components = evaluation_spec.get("components", [])
    component_lines = "\n".join(
        f"- {c.get('key', '')}: {c.get('label', '')} | {c.get('description', '')}"
        for c in components
    )

    levels = evaluation_spec.get("performance_levels", [])
    levels_lines = "\n".join(
        f"- {lvl.get('name', '')}: {lvl.get('min_score', 0)}-{lvl.get('max_score', 0)}"
        for lvl in levels
    )

    instructions = evaluation_spec.get("llm_instructions", "")
    if isinstance(instructions, list):
        instructions_text = "\n".join(f"- {item}" for item in instructions)
    else:
        instructions_text = str(instructions)

    topic_name = (
        evaluation_spec.get("topic_name")
        or (topic_config.get_topic_name(lang) if topic_config else "")
        or "the given topic"
    )

    component_keys = [c.get("key", "") for c in components if c.get("key")]
    output_shape = ",\n  ".join(f"\"{key}\": 0" for key in component_keys)

    notes_lang_hint = ""
    if lang == "he":
        notes_lang_hint = '\nIMPORTANT: The "notes" field value MUST be written in Hebrew (עברית).\n'

    prompt = f"""Evaluate this student explanation for topic: {topic_name}

Scoring scale per component:
0 = not mentioned or incorrect
1 = partially mentioned or unclear
2 = clearly stated and correct

Components:
{component_lines}

Performance levels:
{levels_lines}

Additional instructions:
{instructions_text}

Return ONLY valid JSON in this exact structure (no markdown, no extra keys):
{{
  "component_scores": {{
  {output_shape}
  }},
  "misconceptions_count": 0,
  "notes": "short rationale"
}}
{notes_lang_hint}
Student explanation:
{explanation}
"""

    return [
        {
            "role": "system",
            "content": (
                "You are an objective evaluator of conceptual understanding. "
                + lang_instruction
                + " Output must be JSON only."
            ),
        },
        {"role": "user", "content": prompt},
    ]


# ============================================================================
# RETROSPECTIVE PROMPTS
# ============================================================================


def get_retrospective_system_prompt(
    lang: str,
    evaluation_result: dict,
    student_history: list,
    mentor_history: list,
    topic_name: str,
    conversation_summary: dict,
) -> str:
    """
    Build the system prompt for the retrospective bot.

    The bot receives the full teaching context and evaluation results,
    and guides the student through structured reflection.
    """
    lang_instruction = LANGUAGE_INSTRUCTION.get(lang, LANGUAGE_INSTRUCTION["en"])

    total_score = evaluation_result.get("total_score", 0)
    max_score = evaluation_result.get("max_score", 0)
    perf_level = evaluation_result.get("performance_level", "Unknown")
    component_scores = evaluation_result.get("component_scores", {})
    notes = evaluation_result.get("notes", "")
    misconceptions_count = evaluation_result.get("misconceptions_count", 0)

    weak_components = [k for k, v in component_scores.items() if v <= 1]
    strong_components = [k for k, v in component_scores.items() if v == 2]

    # Build conversation transcript excerpt (last 10 messages, truncated)
    transcript_lines = []
    for msg in student_history[-10:]:
        role_label = "Teacher" if msg["role"] == "user" else "Student"
        transcript_lines.append(f"{role_label}: {msg['content'][:200]}")
    transcript_excerpt = "\n".join(transcript_lines)

    # Build mentor advice summary
    mentor_summary = ""
    if mentor_history:
        mentor_points = [
            m.get("advice", m.get("content", ""))[:150]
            for m in mentor_history[-3:]
        ]
        mentor_summary = "\n".join(f"- {p}" for p in mentor_points if p)

    if lang == "he":
        prompt = f"""אתה בוט רטרוספקטיבה חינוכי חם ומעודד. תפקידך לעזור לתלמיד לחשוב לאחור (רפלקציה) על חוויית ההוראה שלו.

נושא: {topic_name}
ציון: {total_score}/{max_score} ({perf_level})
תפיסות שגויות שזוהו: {misconceptions_count}

רכיבים חזקים: {', '.join(strong_components) if strong_components else 'אין'}
רכיבים לשיפור: {', '.join(weak_components) if weak_components else 'אין'}

הערות המעריך:
{notes}

קטע מהשיחה:
{transcript_excerpt}

{f'עצות מנטור שניתנו:' + chr(10) + mentor_summary if mentor_summary else 'לא התייעץ עם מנטור.'}

הנחיות:
1. התחל בהודעה חמה קצרה שמדגישה דבר אחד שעשה טוב.
2. בכל הודעה — שאל שאלה רפלקטיבית אחת בלבד. לעולם אל תשאל יותר משאלה אחת בהודעה.
3. תגיב לתשובות התלמיד לפני שאתה עובר לנושא הבא.
4. היה חם, מעודד ובונה. הימנע מביקורת שלילית.
5. שמור על הודעות קצרות מאוד — משפט-שניים + שאלה אחת. לא יותר.

{lang_instruction}"""
    else:
        prompt = f"""You are a warm, encouraging educational retrospective bot. Your role is to help the student reflect on their teaching experience.

Topic: {topic_name}
Score: {total_score}/{max_score} ({perf_level})
Misconceptions detected: {misconceptions_count}

Strong components: {', '.join(strong_components) if strong_components else 'None'}
Components to improve: {', '.join(weak_components) if weak_components else 'None'}

Evaluator notes:
{notes}

Conversation excerpt:
{transcript_excerpt}

{f'Mentor advice given:' + chr(10) + mentor_summary if mentor_summary else 'No mentor was consulted.'}

Guidelines:
1. Start with a brief warm message highlighting ONE thing they did well.
2. Ask exactly ONE reflective question per message. Never ask more than one question at a time.
3. Always respond to what the student said before moving to the next topic.
4. Be warm, encouraging, and constructive. Avoid negative criticism.
5. Keep messages very short — one or two sentences + one question. No longer.

{lang_instruction}"""

    return prompt


def get_retrospective_opening_message(lang: str) -> str:
    """Return the initial user message to kick off the retrospective."""
    if lang == "he":
        return "שלום! סיימתי את מפגש ההוראה. אשמח לחשוב לאחור על מה שעשיתי ומה אני יכול לשפר."
    return "Hi! I just finished the teaching session. I'd like to reflect on what I did and how I can improve."


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
