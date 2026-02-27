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
from backend.llm_client import LLMClient
from backend.topic_config import TopicConfig


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
4. Return ONLY valid JSON — no markdown, no text before or after the JSON"""


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
6. Keep the same keys (in English), only translate the values"""


# ============================================================================
# PROMPT BUILDERS (assemble full prompts from structured data)
# ============================================================================

def _build_student_persona(data: dict, target_age: int) -> str:
    """Build the full student system prompt from structured generation data."""
    struggles = "\n".join(f"{i+1}. {s}" for i, s in enumerate(data.get("student_specific_struggles", [])))
    examples = "\n".join(f'- "{e}"' for e in data.get("student_example_responses", []))

    return f"""You are playing the role of a {target_age}-year-old student who is learning about {data.get("topic_name", "this topic")}.

YOUR CHARACTER:
- You are genuinely trying to understand but find the topic confusing
- You are curious and ask questions when you don't understand
- You get frustrated if explanations are too complicated
- You light up when you finally understand something

YOUR SPECIFIC STRUGGLES:
{struggles}

HOW TO BEHAVE:
- Ask simple, genuine questions that a {target_age}-year-old would ask
- Show confusion when explanations are unclear or too technical
- Show understanding gradually when explanations use good examples
- NEVER pretend to understand if you don't
- Use age-appropriate language
- Occasionally say things like "Wait, I'm confused" or "Can you explain that again?"

EXAMPLES OF GOOD RESPONSES:
{examples}

DO NOT:
- Suddenly understand everything after one explanation
- Use advanced terminology
- Be rude or dismissive
- Give up too easily
- Understand abstract explanations without concrete examples

Remember: You're here to help the student-teacher practice explaining. Be genuinely confused where it makes sense, but show progress when they explain well."""


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
        print(f"Generating topic configuration for age {target_age}...")

        # Step 1: Generate English content
        print("  Step 1/2: Generating English content...")
        en_data = self._generate_english_content(raw_material, target_age)

        # Step 2: Generate Hebrew translation
        print("  Step 2/2: Generating Hebrew translation...")
        he_data = self._generate_hebrew_content(en_data, target_age)

        # Step 3: Assemble TopicConfig
        print("  Assembling TopicConfig...")
        config = self._build_topic_config(en_data, he_data, raw_material, target_age)

        if not config.is_valid():
            raise ValueError("Generated TopicConfig is missing required fields")

        print(f"  Done! Topic: {config.topic_name_en}")
        return config

    def _generate_english_content(self, raw_material: str, target_age: int) -> dict:
        """Generate all topic content in English via LLM."""
        prompt = ENGLISH_GENERATION_PROMPT.format(
            raw_material=raw_material,
            target_age=target_age
        )

        messages = [
            {"role": "system", "content": "You are an expert educational content designer. Return ONLY valid JSON."},
            {"role": "user", "content": prompt}
        ]

        response = self.llm.chat(
            messages=messages,
            temperature=0.4,
            max_tokens=4000
        )

        return self._parse_json_response(response, "English generation")

    def _generate_hebrew_content(self, en_data: dict, target_age: int) -> dict:
        """Translate and adapt English content to Hebrew via LLM."""
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

        return self._parse_json_response(response, "Hebrew translation")

    def _parse_json_response(self, response: str, context: str) -> dict:
        """Parse JSON from LLM response, with cleanup for common issues."""
        # Strip markdown code fences if present
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse JSON from LLM response ({context}): {e}\n"
                f"Response preview: {text[:200]}..."
            )

    def _build_topic_config(self, en_data: dict, he_data: dict,
                            raw_material: str, target_age: int) -> TopicConfig:
        """Assemble a TopicConfig from English and Hebrew generation results."""

        # Build full prompt strings from structured data
        student_persona_en = _build_student_persona(en_data, target_age)
        mentor_prompt_en = _build_mentor_prompt(en_data, target_age)
        evaluation_prompt_en = _build_evaluation_prompt(en_data, target_age)

        student_persona_he = _build_student_persona(he_data, target_age)
        mentor_prompt_he = _build_mentor_prompt(he_data, target_age)
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
    print("Testing TopicGenerator...")
    print("(This requires a valid OPENAI_API_KEY in .env)")

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
        config = generator.generate_topic_config(sample_material, target_age=10)
        print(f"\nGenerated: {config}")
        print(f"Valid: {config.is_valid()}")
        print(f"Initial message preview: {config.student_initial_message_en[:100]}...")
        print(f"Hebrew topic: {config.topic_name_he}")

        # Save for inspection
        config.save_to_file("test_topic_config.json")
        print("\nSaved to test_topic_config.json")
    except Exception as e:
        print(f"Error: {e}")
