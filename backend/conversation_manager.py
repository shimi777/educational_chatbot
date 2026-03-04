#!/usr/bin/env python3
"""
Conversation Manager - The Brain of the Educational Chatbot

Manages dual-agent conversations:
1. Struggling Student Agent - the learner
2. Mentor Agent - coaches the student-teacher
3. Evaluation Agent - rates the student-teacher's performance

Now fully generic - all topic-specific content comes from TopicConfig.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Any

from backend.llm_client import LLMClient
from backend.topic_config import TopicConfig
from backend.logger import get_logger
from backend.prompts import (
    get_struggling_student_messages,
    get_mentor_messages,
    get_single_explanation_evaluation_messages,
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
        self._evaluation_spec_cache: Optional[Dict[str, Any]] = None

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

    def _load_evaluation_spec(self) -> Dict[str, Any]:
        """Load and validate the external evaluation spec JSON."""
        if self._evaluation_spec_cache is not None:
            return self._evaluation_spec_cache

        spec_path = Path(__file__).resolve().parent / "evaluation_spec_template.json"
        with spec_path.open("r", encoding="utf-8") as f:
            raw_spec = json.load(f)

        topic_name = raw_spec.get("topic_name")
        if not topic_name and isinstance(raw_spec.get("topic"), dict):
            topic_name = raw_spec["topic"].get("title")
        if not topic_name:
            topic_name = "Configured Topic"

        raw_components = raw_spec.get("components", [])
        if not isinstance(raw_components, list) or not raw_components:
            raise ValueError("Evaluation spec must include at least one component")

        components: List[Dict[str, Any]] = []
        for idx, comp in enumerate(raw_components):
            key = comp.get("key") or comp.get("id")
            label = comp.get("label") or comp.get("name")
            description = comp.get("description")
            if not key or not label or not description:
                raise ValueError(f"Invalid component at index {idx} in evaluation spec")
            components.append({
                "key": str(key),
                "label": str(label),
                "description": str(description),
            })

        raw_levels = raw_spec.get("performance_levels", [])
        if not isinstance(raw_levels, list) or not raw_levels:
            raise ValueError("Evaluation spec must include performance_levels")
        performance_levels: List[Dict[str, Any]] = []
        for lvl in raw_levels:
            name = lvl.get("name") or lvl.get("label") or lvl.get("id") or "Unclassified"
            min_score = lvl.get("min_score", lvl.get("min_score_inclusive", 0))
            max_score = lvl.get("max_score", lvl.get("max_score_inclusive", 0))
            try:
                min_score = int(round(float(min_score)))
                max_score = int(round(float(max_score)))
            except (TypeError, ValueError):
                continue
            performance_levels.append({
                "name": str(name),
                "min_score": min_score,
                "max_score": max_score,
            })
        if not performance_levels:
            raise ValueError("Evaluation spec contains no usable performance levels")

        instructions = raw_spec.get("llm_instructions")
        if instructions is None:
            instructions = [
                "Assign each component a score of exactly 0, 1, or 2.",
                "Use score 0 when missing or incorrect.",
                "Use score 1 when partial or unclear.",
                "Use score 2 when clear and correct.",
                "Return valid JSON only.",
            ]
        elif isinstance(instructions, str):
            instructions = [instructions]

        spec = {
            "topic_name": topic_name,
            "components": components,
            "performance_levels": performance_levels,
            "llm_instructions": instructions,
        }
        self._evaluation_spec_cache = spec
        return spec

    def _teacher_messages(self) -> List[str]:
        """Return teacher explanation messages from conversation history."""
        return [
            msg["content"].strip()
            for msg in self.student_history
            if msg.get("role") == "user" and isinstance(msg.get("content"), str) and msg["content"].strip()
        ]

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse model response into JSON dict with mild recovery strategies."""
        if not response or not response.strip():
            return {}

        text = response.strip()
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            text = text[first_brace:last_brace + 1]

        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _normalize_component_scores(self, raw: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize model output:
        - Missing components default to 0
        - Scores are clamped to 0..2
        """
        raw_scores = raw.get("component_scores", {})
        if not isinstance(raw_scores, dict):
            raw_scores = {}

        component_scores: Dict[str, int] = {}
        for comp in spec["components"]:
            key = comp["key"]
            score = raw_scores.get(key, 0)
            try:
                score = int(score)
            except (TypeError, ValueError):
                score = 0
            component_scores[key] = max(0, min(2, score))

        misconceptions_count = raw.get("misconceptions_count", 0)
        if isinstance(misconceptions_count, bool):
            misconceptions_count = int(misconceptions_count)
        elif not isinstance(misconceptions_count, int):
            misconceptions_count = 0
        misconceptions_count = max(0, misconceptions_count)

        notes = raw.get("notes", "")
        if not isinstance(notes, str):
            notes = str(notes)

        return {
            "component_scores": component_scores,
            "misconceptions_count": misconceptions_count,
            "notes": notes.strip(),
        }

    def _compute_performance_level(self, total_score: int, spec: Dict[str, Any]) -> str:
        """Map a numeric score to a named performance level."""
        for level in spec.get("performance_levels", []):
            if level.get("min_score", 0) <= total_score <= level.get("max_score", 0):
                return level.get("name", "Unknown")
        return "Unclassified"

    def _evaluate_explanation_with_llm(self, explanation: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate one explanation using the shared LLM client and spec."""
        messages = get_single_explanation_evaluation_messages(
            explanation=explanation,
            evaluation_spec=spec,
            lang=self.lang,
            topic_config=self.topic_config,
        )
        raw_text = self.llm.chat(
            messages=messages,
            temperature=0.0,
            max_tokens=500,
        )
        raw_json = self._parse_json_response(raw_text)
        normalized = self._normalize_component_scores(raw_json, spec)
        total_score = sum(normalized["component_scores"].values())
        max_score = len(spec["components"]) * 2
        return {
            "component_scores": normalized["component_scores"],
            "total_score": total_score,
            "max_score": max_score,
            "performance_level": self._compute_performance_level(total_score, spec),
            "components_correct_count": sum(
                1 for score in normalized["component_scores"].values() if score == 2
            ),
            "misconceptions_count": normalized["misconceptions_count"],
            "notes": normalized["notes"],
        }

    def _build_improvement(self, before_eval: Dict[str, Any], after_eval: Dict[str, Any]) -> Dict[str, int]:
        """Compute improvement deltas between two evaluations."""
        return {
            "score_delta": after_eval["total_score"] - before_eval["total_score"],
            "correct_components_delta": (
                after_eval["components_correct_count"] - before_eval["components_correct_count"]
            ),
            "misconceptions_delta": (
                after_eval["misconceptions_count"] - before_eval["misconceptions_count"]
            ),
        }

    def evaluate_performance(self) -> Dict[str, Any]:
        """
        Evaluate the student-teacher's performance using topic-agnostic components.

        Returns:
            Structured evaluation dictionary.
        """
        teacher_messages = self._teacher_messages()
        if not teacher_messages:
            msg = (
                "No conversation to evaluate. Send at least one message to the student."
                if self.lang == "en"
                else "אין שיחה להערכה. שלח לפחות הודעה אחת לתלמיד."
            )
            return {
                "component_scores": {},
                "total_score": 0,
                "max_score": 0,
                "performance_level": "Not Evaluated",
                "components_correct_count": 0,
                "misconceptions_count": 0,
                "comparison": {
                    "before": None,
                    "after": None,
                    "improvement": None,
                    "reason": msg,
                },
                "notes": msg,
            }

        spec = self._load_evaluation_spec()
        after_eval = self._evaluate_explanation_with_llm(teacher_messages[-1], spec)

        before_eval = None
        improvement = None
        reason = None
        if len(teacher_messages) >= 2:
            before_eval = self._evaluate_explanation_with_llm(teacher_messages[0], spec)
            improvement = self._build_improvement(before_eval, after_eval)
        else:
            reason = (
                "Need at least two teacher explanations for improvement comparison."
                if self.lang == "en"
                else "נדרשות לפחות שתי הודעות של המתרגל להשוואת שיפור."
            )

        result = {
            "component_scores": after_eval["component_scores"],
            "total_score": after_eval["total_score"],
            "max_score": after_eval["max_score"],
            "performance_level": after_eval["performance_level"],
            "components_correct_count": after_eval["components_correct_count"],
            "misconceptions_count": after_eval["misconceptions_count"],
            "comparison": {
                "before": before_eval,
                "after": after_eval,
                "improvement": improvement,
                "reason": reason,
            },
            "notes": after_eval.get("notes", ""),
        }

        logger.info(
            "Evaluation complete | turns=%d | mentor_consultations=%d | total=%s/%s",
            self.turn_count,
            len(self.mentor_history),
            result["total_score"],
            result["max_score"],
        )
        return result

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
