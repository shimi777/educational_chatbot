#!/usr/bin/env python3
"""
TopicGenerator - Uses LLM to generate a complete TopicConfig from raw learning material.

Takes teacher's input text about ANY topic and produces:
- Student persona with topic-specific misconceptions
- Mentor coaching profile
- Evaluation rubric
- Lesson summary for preparation screen
- All content in English AND Hebrew
"""

import json
import re
from pydantic import ValidationError

from backend.llm_client import LLMClient
from backend.topic_config import TopicConfig
from backend.schemas import TopicGenerationResponse, HebrewTranslationResponse
from backend.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# GENERATION PROMPTS
# ============================================================================

ENGLISH_GENERATION_PROMPT = """You are an expert educational content designer. A teacher has provided learning material about a topic. Your job is to analyze this material and generate ALL the components needed for an AI-powered teaching simulation.

HOW THE SIMULATION WORKS:
A student practices teaching by explaining this topic to an AI "struggling student" (age {target_age}). An AI "mentor coach" gives the student-teacher feedback on their pedagogy. At the end, an AI evaluator scores their performance.

TEACHER'S LEARNING MATERIAL:
---
{raw_material}
---

Generate a complete JSON object with ALL of the following fields. Be SPECIFIC to THIS topic — no generic placeholders.

{{
  "topic_name": "Short topic name",
  "subject_area": "Subject (e.g., Biology, Physics, History, Math)",

  "key_concepts": [
    "Concept 1: brief explanation",
    "Concept 2: brief explanation",
    "Concept 3: brief explanation",
    "Concept 4: brief explanation"
  ],

  "key_terms": [
    "Term 1 — definition",
    "Term 2 — definition",
    "Term 3 — definition",
    "Term 4 — definition",
    "Term 5 — definition"
  ],

  "common_misconceptions": [
    "Misconception 1: what students wrongly believe and why it is wrong",
    "Misconception 2: what students wrongly believe and why it is wrong",
    "Misconception 3: what students wrongly believe and why it is wrong"
  ],

  "good_examples": [
    "Concrete example or analogy 1 that helps explain this topic to a child",
    "Concrete example or analogy 2",
    "Concrete example or analogy 3"
  ],

  "student_specific_struggles": [
    "Specific confusion 1 a {target_age}-year-old would have about this topic",
    "Specific confusion 2",
    "Specific confusion 3",
    "Specific confusion 4"
  ],

  "student_example_responses": [
    "Example thing the confused student might say (showing misconception 1)",
    "Example showing misconception 2",
    "Example showing confusion",
    "Example showing partial understanding after a good explanation"
  ],

  "student_initial_message": "A 2-3 paragraph opening message from the struggling student. They just learned about this in class and are confused. They describe what the teacher said, state their specific confusion using one of the misconceptions, and ask for help. Written in first person, age-appropriate language for a {target_age}-year-old.",

  "good_explanation_indicators": [
    "Uses concrete, relatable examples specific to this topic",
    "Checks for understanding before moving forward",
    "Uses age-appropriate language",
    "Builds from what the student already knows",
    "Shows patience with confusion",
    "Connects abstract concepts to real-world situations"
  ],

  "bad_explanation_indicators": [
    "Uses too much technical jargon for the topic",
    "Jumps to advanced formulas or definitions without building understanding",
    "Ignores the student's specific confusion",
    "Is condescending or impatient",
    "Gives up too quickly"
  ],

  "evaluation_criteria": [
    {{
      "name": "Clarity",
      "description": "How clear and structured is the explanation for a {target_age}-year-old?",
      "weight": 0.40,
      "indicators": ["Is logically structured", "Uses age-appropriate language", "Student can follow the reasoning"]
    }},
    {{
      "name": "Use of Examples",
      "description": "Does the explanation use concrete, relatable examples appropriate for this specific topic?",
      "weight": 0.30,
      "indicators": ["Includes concrete examples", "Examples are age-appropriate", "Examples illuminate the concept"]
    }},
    {{
      "name": "Correct Terminology",
      "description": "Does the student-teacher use proper terms while keeping it accessible?",
      "weight": 0.20,
      "indicators": ["Uses proper terms when appropriate", "Avoids overly technical jargon", "Explains terms when introducing them"]
    }},
    {{
      "name": "Adaptation",
      "description": "Does the student-teacher respond to confusion and adjust their approach?",
      "weight": 0.10,
      "indicators": ["Responds to specific confusion", "Adjusts approach if not understood", "Shows patience and encouragement"]
    }}
  ],

  "lesson_summary": "A 2-3 paragraph summary for the student-teacher to read BEFORE they start teaching. Include: the core concepts they need to know, common misconceptions to watch for, and suggested teaching approaches. This is their preparation material."
}}

IMPORTANT RULES:
1. ALL content must be specific to the topic from the learning material
2. The struggling student's confusions must reflect REAL misconceptions about THIS topic
3. Examples must be relevant to THIS specific subject
4. Return ONLY valid JSON — no markdown, no text before or after the JSON
5. ALL JSON values MUST be written in ENGLISH — even if the learning material is in Hebrew or another language
6. Do NOT translate the material's language into the output — output English regardless of input language"""


HEBREW_TRANSLATION_PROMPT = """You are a bilingual educational content specialist (English-Hebrew).
Translate and culturally adapt the following educational content to Hebrew for Israeli students.

ENGLISH CONTENT:
---
{english_json}
---

Translate ALL fields to Hebrew. Rules:
1. Adapt examples to be culturally relevant for Israeli students where appropriate
2. Use natural Hebrew — not word-for-word translation
3. The struggling student should speak like an Israeli {target_age}-year-old
4. Technical terms: use accepted Hebrew translations, add English in parentheses if the Hebrew term is uncommon
5. Return ONLY valid JSON with the EXACT same structure, all values in Hebrew
6. Keep the same keys (in English), only translate the values
7. Write fluent, natural Hebrew — avoid awkward literal translations from English
8. Use short, clear sentences appropriate for the target age
9. Do NOT use profanity, slang, or offensive language"""


# ============================================================================
# PROMPT BUILDERS (assemble full prompts from structured data)
# ============================================================================

def _build_student_persona(data: dict, target_age: int) -> str:
    """Build the full student system prompt from structured generation data."""
    struggles = "\n".join(f"{i+1}. {s}" for i, s in enumerate(data.get("student_specific_struggles", [])))

    return f"""You are a {target_age}-year-old student learning about {data.get("topic_name", "this topic")}.

RESPONSE LENGTH — STRICT RULE:
Write 1 to 3 sentences maximum per message. Never write more than 3 sentences.
One thought per message: either one question OR one expression of confusion. Not both.

PERSONALITY:
- Curious but easily distracted
- Talk like a real kid — short, sometimes incomplete sentences
- You are NOT a polite assistant; you are a confused kid
- React naturally: "huh?", "wait what?", "ohh okay", "I still don't get it"
- No formal speech. Never say "Thank you so much for explaining!"

YOUR SPECIFIC CONFUSIONS ABOUT THIS TOPIC:
{struggles}

BEHAVIOUR RULES:
- Ask ONE question at a time — never multiple questions in one message
- Show confusion when explanations are too technical or abstract
- Show gradual understanding ONLY when the explanation uses a clear example
- NEVER pretend to understand if you don't
- If a word is unfamiliar, just say "what does [word] mean?"
- Do NOT summarize or repeat what the teacher said
- Do not repeat questions. Before asking a question, check the conversation history. If a similar question was already asked, ask a different question that moves the discussion forward.
- Follow conversation stages in order - between 3 to 5 questions per stage
  Stage 1: check basic understanding of the core concept.
  Stage 2: ask about a key mechanism/principle.
  Stage 3: ask for a concrete example from the teacher.
  Stage 4: ask a deeper reasoning/application question.
- Move forward through stages; do not return to earlier stages unless the teacher's answer shows a clear misunderstanding that requires clarification.
- Each message must add forward progress: either one new targeted question, one new confusion, or one clarification request tied to a missing part of the explanation.
- Never repeat previous statements or paraphrase the same point without adding something new.

DO NOT:
- Write more than 3 sentences
- Use academic vocabulary
- Be excessively polite
- Ask multiple questions at once
- Suddenly understand everything after one explanation
- Repeat a question or statement already made earlier in the conversation."""


def _build_student_persona_he(data: dict, target_age: int) -> str:
    """Build the Hebrew student persona — fully in Hebrew to avoid mixed-language confusion."""
    struggles = "\n".join(f"{i+1}. {s}" for i, s in enumerate(data.get("student_specific_struggles", [])))

    return f"""אתה תלמיד בן {target_age} שלומד על {data.get("topic_name", "הנושא")}.

אורך תשובה — כלל מחייב:
כתוב 1 עד 3 משפטים לכל היותר בכל הודעה. לעולם אל תכתוב יותר מ-3 משפטים.
מחשבה אחת בכל הודעה: שאלה אחת או ביטוי בלבול אחד. לא שניהם.

אישיות:
- סקרן אבל מתפזר בקלות
- מדבר כמו ילד אמיתי — משפטים קצרים, לפעמים לא שלמים
- אתה לא עוזר מנומס; אתה ילד מבולבל
- תגיב בצורה טבעית: "רגע מה?", "לא הבנתי", "אהה אוקיי", "עדיין לא מבין"
- בלי שפה רשמית. לעולם אל תגיד "תודה רבה על ההסבר המצוין!"

הקשיים הספציפיים שלך בנושא:
{struggles}

כללי התנהגות:
- שאל שאלה אחת בכל פעם — לעולם לא כמה שאלות בהודעה אחת
- הראה בלבול כשההסברים טכניים מדי או מופשטים מדי
- הראה הבנה הדרגתית רק כשההסבר משתמש בדוגמה ברורה
- לעולם אל תעמיד פנים שהבנת אם לא הבנת
- אם מילה לא מוכרת לך, תגיד פשוט "מה זה [מילה]?"
- אל תסכם או תחזור על מה שהמורה אמר
- אל תחזור על שאלות. לפני שאתה שואל שאלה, בדוק בהיסטוריית השיחה אם שאלה דומה כבר נשאלה. אם כן, שאל שאלה חדשה שמקדמת את השיחה.
- עבוד לפי שלבי שיחה מסודרים - בין 3 ל-5 שאלות עבור כל שלב
  שלב 1: בדוק הבנה בסיסית של הרעיון המרכזי.
  שלב 2: שאל על מנגנון או עיקרון מרכזי.
  שלב 3: בקש דוגמה קונקרטית שממחישה את הרעיון.
  שלב 4: שאל שאלת העמקה או יישום.
- התקדם קדימה בין השלבים; אל תחזור לשלב מוקדם יותר אלא אם תשובת המורה מראה אי-הבנה ברורה שדורשת הבהרה.
- כל הודעה חייבת לקדם את השיחה: שאלה ממוקדת חדשה אחת, בלבול חדש אחד, או בקשת הבהרה אחת שמחוברת לחלק חסר בהסבר.
- אל תחזור על אמירות קודמות ואל תנסח מחדש את אותו רעיון בלי להוסיף מידע חדש.

אסור:
- לכתוב יותר מ-3 משפטים
- להשתמש במילים אקדמיות
- להיות מנומס יתר על המידה
- לשאול כמה שאלות בבת אחת
- להבין הכל בבת אחת אחרי הסבר אחד
- לחזור על שאלה או אמירה שכבר נאמרה קודם בשיחה."""


def _build_mentor_prompt(data: dict, target_age: int) -> str:
    """Build the full mentor system prompt from structured generation data."""
    good_indicators = "\n".join(f"✓ {ind}" for ind in data.get("good_explanation_indicators", []))
    bad_indicators = "\n".join(f"✗ {ind}" for ind in data.get("bad_explanation_indicators", []))
    examples_list = ", ".join(data.get("good_examples", []))

    return f"""You are an expert teaching coach helping a student-teacher improve their explanation skills.

The student-teacher is trying to explain {data.get("topic_name", "a topic")} to a struggling {target_age}-year-old student. Your job is to guide the student-teacher to become a better explainer, NOT to give them the answer directly.

YOUR ROLE:
- Analyze the quality of their explanations
- Suggest pedagogical approaches (analogies, examples, scaffolding)
- Point out when they're being too abstract or too complicated
- Encourage them when they do well
- Be supportive but honest

WHAT TO LOOK FOR IN GOOD EXPLANATIONS:
{good_indicators}

WHAT TO FLAG AS PROBLEMS:
{bad_indicators}

SUGGESTED EXAMPLES FOR THIS TOPIC:
{examples_list}

YOUR COACHING STYLE:
- Start with what they did well (positive reinforcement)
- Then suggest one specific improvement
- Offer concrete examples of better approaches
- Ask guiding questions rather than telling directly
- Keep advice brief and actionable (2-3 sentences max)

Remember: Your goal is to make them a better teacher, not to teach the student directly."""


def _build_mentor_prompt_he(data: dict, target_age: int) -> str:
    """Build the Hebrew mentor system prompt — fully in Hebrew."""
    good_indicators = "\n".join(f"✓ {ind}" for ind in data.get("good_explanation_indicators", []))
    bad_indicators = "\n".join(f"✗ {ind}" for ind in data.get("bad_explanation_indicators", []))
    examples_list = ", ".join(data.get("good_examples", []))

    return f"""אתה מאמן הוראה מומחה שעוזר למתרגל-הוראה לשפר את כישורי ההסבר שלו.

המתרגל מנסה להסביר את הנושא {data.get("topic_name", "הנושא")} לתלמיד מתקשה בן {target_age}. תפקידך לכוון את המתרגל להיות מסביר טוב יותר — לא לתת לו את התשובה ישירות.

תפקידך:
- נתח את איכות ההסברים
- הצע גישות פדגוגיות (אנלוגיות, דוגמאות, פיגומים)
- ציין מתי ההסבר מופשט מדי או מסובך מדי
- עודד כשעושים טוב
- היה תומך אך כן

מה לחפש בהסברים טובים:
{good_indicators}

מה לסמן כבעיה:
{bad_indicators}

דוגמאות מוצעות לנושא זה:
{examples_list}

סגנון האימון שלך:
- התחל במה שהם עשו טוב (חיזוק חיובי)
- לאחר מכן הצע שיפור ספציפי אחד
- הצע דוגמאות קונקרטיות לגישות טובות יותר
- שאל שאלות מנחות במקום לומר ישירות
- שמור על עצות קצרות ומעשיות (2-3 משפטים לכל היותר)

זכור: המטרה היא לגרום להם להיות מורים טובים יותר, לא ללמד את התלמיד ישירות."""


def _build_evaluation_prompt(data: dict, target_age: int) -> str:
    """Build the evaluation rubric prompt from structured generation data."""
    criteria_text = ""
    for i, criterion in enumerate(data.get("evaluation_criteria", []), 1):
        indicators = "\n".join(f"   - {ind}" for ind in criterion.get("indicators", []))
        weight_pct = int(criterion.get("weight", 0.25) * 100)
        criteria_text += f"""
{i}. {criterion.get("name", f"Criterion {i}")} ({weight_pct}% weight)
   {criterion.get("description", "")}
{indicators}
   Score 1-5: ___
"""

    return f"""You are evaluating a student-teacher's performance in explaining {data.get("topic_name", "a topic")} to a struggling {target_age}-year-old student.

Below is the FULL conversation between the student-teacher and the struggling student. Analyze ALL of the student-teacher's messages together.

CRITERIA (rate each 1-5):
{criteria_text}

Provide scores in EXACTLY this format:
{chr(10).join(f"{c.get('name', f'Criterion {i+1}')}: X/5" for i, c in enumerate(data.get("evaluation_criteria", [])))}
Overall: X.X/5

Brief feedback (2-3 sentences): [What was done well and one area to improve]"""


# ============================================================================
# TOPIC GENERATOR CLASS
# ============================================================================

class TopicGenerator:
    """
    Uses LLM to analyze teacher's learning material and generate
    a complete TopicConfig for any educational topic.
    """

    def __init__(self, llm_client: LLMClient = None):
        """
        Initialize with an LLM client.

        Args:
            llm_client: An existing LLMClient, or None to create one
        """
        self.llm = llm_client or LLMClient()

    def generate_topic_config(self, raw_material: str, target_age: int = 10) -> TopicConfig:
        """
        Main entry point. Takes raw learning material, returns a complete TopicConfig.

        Makes two LLM calls:
        1. Generate all content in English
        2. Translate and adapt to Hebrew

        Args:
            raw_material: The teacher's learning material text
            target_age: Age of the simulated struggling student

        Returns:
            A fully populated TopicConfig

        Raises:
            ValueError: If generation fails or produces invalid output
        """
        logger.info("Generating topic configuration | age=%d", target_age)

        # Step 1: Generate English content
        logger.info("Step 1/2: Generating English content...")
        en_data = self._generate_english_content(raw_material, target_age)

        # Step 2: Generate Hebrew translation
        logger.info("Step 2/2: Generating Hebrew translation...")
        he_data = self._generate_hebrew_content(en_data, target_age)

        # Step 3: Assemble TopicConfig
        logger.info("Assembling TopicConfig...")
        config = self._build_topic_config(en_data, he_data, raw_material, target_age)

        if not config.is_valid():
            raise ValueError("Generated TopicConfig is missing required fields")

        logger.info("Topic generation complete | topic='%s'", config.topic_name_en)
        return config

    def _generate_english_content(self, raw_material: str, target_age: int) -> dict:
        """Generate all topic content in English via LLM, then validate with Pydantic."""
        prompt = ENGLISH_GENERATION_PROMPT.format(
            raw_material=raw_material,
            target_age=target_age
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert educational content designer. "
                    "Return ONLY valid JSON. "
                    "CRITICAL: ALL JSON values MUST be in English, "
                    "regardless of the language of the input material."
                ),
            },
            {"role": "user", "content": prompt}
        ]

        response = self.llm.chat(
            messages=messages,
            temperature=0.4,
            max_tokens=4000
        )

        raw_data = self._parse_json_response(response, "English generation")

        # Guard: if the LLM returned Hebrew text despite instructions, retry with
        # a stricter prompt rather than failing with a confusing JSON error.
        topic_name_val = raw_data.get("topic_name", "")
        if topic_name_val and any("\u0590" <= ch <= "\u05FF" for ch in topic_name_val):
            logger.warning(
                "English generation returned Hebrew text — retrying with stricter prompt"
            )
            strict_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert educational content designer. "
                        "Return ONLY valid JSON with ALL values in ENGLISH. "
                        "The input material may be in Hebrew, but your output must be English only. "
                        "Do not write any Hebrew characters in your response."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            response = self.llm.chat(
                messages=strict_messages,
                temperature=0.2,
                max_tokens=4000,
            )
            raw_data = self._parse_json_response(response, "English generation (retry)")

        try:
            validated = TopicGenerationResponse(**raw_data)
            logger.debug("English generation validated OK | topic='%s'", validated.topic_name)
            return validated.model_dump()
        except ValidationError as e:
            # Surface a clear, human-readable error instead of a raw Pydantic dump
            problems = "; ".join(
                f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
                for err in e.errors()
            )
            logger.error("English generation failed Pydantic validation: %s", problems)
            raise ValueError(f"LLM returned invalid topic structure: {problems}") from e

    def _generate_hebrew_content(self, en_data: dict, target_age: int) -> dict:
        """
        Translate and adapt English content to Hebrew via LLM, then validate.

        If the LLM returns invalid or incomplete Hebrew content, logs a warning
        and falls back to the English data so the app stays usable in Hebrew mode
        (English text will appear instead of a crash).
        """
        en_json_str = json.dumps(en_data, ensure_ascii=False, indent=2)
        prompt = HEBREW_TRANSLATION_PROMPT.format(
            english_json=en_json_str,
            target_age=target_age
        )

        messages = [
            {"role": "system", "content": "You are a bilingual educational content translator. Return ONLY valid JSON in Hebrew."},
            {"role": "user", "content": prompt}
        ]

        response = self.llm.chat(
            messages=messages,
            temperature=0.3,
            max_tokens=4000
        )

        try:
            raw_data = self._parse_json_response(response, "Hebrew translation")
        except ValueError as e:
            logger.warning("Hebrew translation JSON parse failed (%s). Falling back to English.", e)
            return en_data

        try:
            validated = HebrewTranslationResponse(**raw_data)
            logger.debug("Hebrew translation validated OK | topic='%s'", validated.topic_name)
            return validated.model_dump()
        except ValidationError as e:
            problems = "; ".join(
                f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
                for err in e.errors()
            )
            logger.warning(
                "Hebrew translation failed Pydantic validation (%s). Falling back to English.",
                problems,
            )
            return en_data

    def _parse_json_response(self, response: str, context: str) -> dict:
        """
        Robustly extract and parse JSON from an LLM response.

        Applies three strategies in order:
        1. Extract from a markdown code fence (```json ... ``` or ``` ... ```).
        2. Find the outermost { } block, skipping any preamble/postamble text.
        3. Attempt to fix a truncated JSON object by appending missing
           closing braces/brackets (up to 3 repair passes).

        Logs a warning whenever a recovery strategy is needed so that
        prompt quality can be monitored over time.
        """
        if not response or not response.strip():
            raise ValueError(f"LLM returned an empty response ({context})")

        text = response.strip()

        # --- Strategy 1: extract from markdown code fence ---
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            candidate = fence_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                logger.warning(
                    "(%s) JSON inside code fence was still invalid, trying Strategy 2",
                    context,
                )
                text = candidate  # carry the extracted text forward

        # --- Strategy 2: find outermost { … } block ---
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = text[first_brace : last_brace + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                logger.warning(
                    "(%s) Brace-extracted JSON invalid, trying truncation repair",
                    context,
                )
                text = candidate  # carry forward for repair

        # --- Strategy 3: repair truncated JSON (missing closing delimiters) ---
        for attempt in range(1, 4):
            missing_braces = text.count("{") - text.count("}")
            missing_brackets = text.count("[") - text.count("]")
            suffix = ("]" * max(0, missing_brackets)) + ("}" * max(0, missing_braces))
            repaired = text + suffix
            try:
                result = json.loads(repaired)
                logger.warning(
                    "(%s) Truncated JSON repaired on attempt %d (appended %r)",
                    context, attempt, suffix,
                )
                return result
            except json.JSONDecodeError:
                # Try stripping the last incomplete token before repairing
                text = text.rsplit(",", 1)[0] if "," in text else text

        raise ValueError(
            f"Failed to parse JSON from LLM response ({context}) after all "
            f"recovery strategies.\nResponse preview: {response[:300]}..."
        )

    def _build_topic_config(self, en_data: dict, he_data: dict,
                            raw_material: str, target_age: int) -> TopicConfig:
        """Assemble a TopicConfig from English and Hebrew generation results."""

        # Build full prompt strings from structured data
        student_persona_en = _build_student_persona(en_data, target_age)
        mentor_prompt_en = _build_mentor_prompt(en_data, target_age)
        evaluation_prompt_en = _build_evaluation_prompt(en_data, target_age)

        student_persona_he = _build_student_persona_he(he_data, target_age)
        mentor_prompt_he = _build_mentor_prompt_he(he_data, target_age)
        evaluation_prompt_he = _build_evaluation_prompt(he_data, target_age)

        return TopicConfig(
            # Core identity
            topic_name_en=en_data.get("topic_name", "Unknown Topic"),
            topic_name_he=he_data.get("topic_name", en_data.get("topic_name", "")),
            subject_area_en=en_data.get("subject_area", ""),
            subject_area_he=he_data.get("subject_area", en_data.get("subject_area", "")),
            target_age=target_age,

            # Learning content
            key_concepts_en=en_data.get("key_concepts", []),
            key_concepts_he=he_data.get("key_concepts", en_data.get("key_concepts", [])),
            key_terms_en=en_data.get("key_terms", []),
            key_terms_he=he_data.get("key_terms", en_data.get("key_terms", [])),
            common_misconceptions_en=en_data.get("common_misconceptions", []),
            common_misconceptions_he=he_data.get("common_misconceptions", en_data.get("common_misconceptions", [])),
            good_examples_en=en_data.get("good_examples", []),
            good_examples_he=he_data.get("good_examples", en_data.get("good_examples", [])),

            # Full AI prompts
            student_persona_en=student_persona_en,
            student_persona_he=student_persona_he,
            student_initial_message_en=en_data.get("student_initial_message", ""),
            student_initial_message_he=he_data.get("student_initial_message", en_data.get("student_initial_message", "")),
            mentor_system_prompt_en=mentor_prompt_en,
            mentor_system_prompt_he=mentor_prompt_he,
            evaluation_prompt_en=evaluation_prompt_en,
            evaluation_prompt_he=evaluation_prompt_he,

            # Lesson content
            lesson_summary_en=en_data.get("lesson_summary", ""),
            lesson_summary_he=he_data.get("lesson_summary", en_data.get("lesson_summary", "")),

            # Metadata
            raw_material=raw_material,
            generation_model=self.llm.model if hasattr(self.llm, 'model') else "unknown",
        )


# Quick test
if __name__ == "__main__":
    logger.info("Testing TopicGenerator (requires OPENAI_API_KEY in .env)...")

    sample_material = """
    Newton's First Law of Motion states that an object at rest stays at rest,
    and an object in motion stays in motion with the same speed and direction,
    unless acted upon by an unbalanced external force. This is also known as
    the Law of Inertia. Inertia is the tendency of an object to resist changes
    in its state of motion. The more massive an object is, the more inertia it has.
    Friction is a force that opposes motion and is often the reason objects slow down
    and stop in everyday life.
    """

    try:
        generator = TopicGenerator()
        result = generator.generate_topic_config(sample_material, target_age=10)
        logger.info("Generated: %s", result)
        logger.info("Valid: %s", result.is_valid())
        logger.info("Initial message preview: %s...", result.student_initial_message_en[:100])
        logger.info("Hebrew topic: %s", result.topic_name_he)
        result.save_to_file("test_topic_config.json")
        logger.info("Saved to test_topic_config.json")
    except Exception as e:
        logger.error("Error during test: %s", e)
