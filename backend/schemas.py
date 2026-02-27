#!/usr/bin/env python3
"""
Pydantic validation schemas for LLM-generated JSON responses.

Sprint 2 addition — every LLM response that should be JSON is parsed
and validated here before it is used anywhere in the application.

Why this matters:
- LLMs hallucinate, truncate, or omit fields.
- Catching the error at the boundary (here) gives a clear message
  instead of a cryptic KeyError/AttributeError inside business logic.
- The Hebrew translation can fall back to English gracefully when the
  LLM returns an incomplete Hebrew response.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class EvaluationCriterion(BaseModel):
    """One row of the evaluation rubric sent to the evaluator LLM."""
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    weight: float = Field(ge=0.0, le=1.0)
    indicators: List[str] = Field(min_length=1)


# ---------------------------------------------------------------------------
# English generation response
# ---------------------------------------------------------------------------

class TopicGenerationResponse(BaseModel):
    """
    Schema for the English-content LLM call in TopicGenerator.
    All fields are required; lists must be non-empty.
    """

    topic_name: str = Field(min_length=1, max_length=200)
    subject_area: str = Field(min_length=1)

    key_concepts: List[str] = Field(min_length=2)
    key_terms: List[str] = Field(min_length=2)
    common_misconceptions: List[str] = Field(min_length=1)
    good_examples: List[str] = Field(min_length=1)

    student_specific_struggles: List[str] = Field(min_length=1)
    student_example_responses: List[str] = Field(min_length=1)
    student_initial_message: str = Field(min_length=20)

    good_explanation_indicators: List[str] = Field(min_length=1)
    bad_explanation_indicators: List[str] = Field(min_length=1)

    evaluation_criteria: List[EvaluationCriterion] = Field(min_length=1)

    lesson_summary: str = Field(min_length=20)

    @field_validator("topic_name", "subject_area", "student_initial_message",
                     "lesson_summary", mode="before")
    @classmethod
    def strip_whitespace(cls, v):
        """Strip accidental leading/trailing whitespace from string fields."""
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "TopicGenerationResponse":
        """Evaluation criterion weights must sum to approximately 1.0."""
        total = sum(c.weight for c in self.evaluation_criteria)
        if not (0.85 <= total <= 1.15):
            raise ValueError(
                f"evaluation_criteria weights sum to {total:.2f}, expected ~1.0"
            )
        return self


# ---------------------------------------------------------------------------
# Hebrew translation response
# ---------------------------------------------------------------------------

class HebrewTranslationResponse(BaseModel):
    """
    Schema for the Hebrew-translation LLM call in TopicGenerator.

    Slightly more lenient than the English schema (shorter min lengths)
    because Hebrew text can be naturally shorter.  Falls back to English
    values if a field is missing — handled at the call site.
    """

    topic_name: str = Field(min_length=1, max_length=200)
    subject_area: str = Field(min_length=1)

    key_concepts: List[str] = Field(min_length=1)
    key_terms: List[str] = Field(min_length=1)
    common_misconceptions: List[str] = Field(min_length=1)
    good_examples: List[str] = Field(min_length=1)

    student_specific_struggles: List[str] = Field(min_length=1)
    student_example_responses: List[str] = Field(min_length=1)
    student_initial_message: str = Field(min_length=5)

    good_explanation_indicators: List[str] = Field(min_length=1)
    bad_explanation_indicators: List[str] = Field(min_length=1)

    evaluation_criteria: List[EvaluationCriterion] = Field(min_length=1)

    lesson_summary: str = Field(min_length=5)

    @field_validator("topic_name", "subject_area", "student_initial_message",
                     "lesson_summary", mode="before")
    @classmethod
    def strip_whitespace(cls, v):
        return v.strip() if isinstance(v, str) else v
