from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ConstraintDimension = Literal[
    "taste",
    "texture",
    "temperature",
    "cuisine",
    "dish_type",
    "ingredient",
    "diet",
    "health",
    "price",
    "meal",
    "other",
]
ConstraintStrength = Literal["required", "strong", "preferred", "weak"]
EvidenceKind = Literal[
    "official_menu",
    "official_website",
    "provider_query",
    "restaurant_tag",
]


class IntentConstraint(BaseModel):
    """One independently scoreable part of a food craving."""

    id: str
    dimension: ConstraintDimension
    value: str
    polarity: Literal["include", "exclude"]
    strength: ConstraintStrength


class SearchQuerySpec(BaseModel):
    """A dish-oriented retrieval query and the constraints it represents."""

    text: str
    constraint_ids: list[str]


class CravingIntent(BaseModel):
    """Structured interpretation used by every downstream ranking stage."""

    summary: str
    constraints: list[IntentConstraint]
    candidate_dishes: list[str]
    search_queries: list[SearchQuerySpec]


class EvidenceItem(BaseModel):
    """A bounded, attributable fact that may support a recommendation."""

    id: str
    kind: EvidenceKind
    label: str
    detail: str = ""
    source_url: str | None = None
    quality: float = Field(ge=0, le=1)
    declared_constraint_ids: list[str] = Field(default_factory=list)
    retrieval_rank: int | None = Field(default=None, ge=1)


class EvidenceLink(BaseModel):
    """A model judgment connecting known evidence to known constraints."""

    evidence_id: str
    constraint_ids: list[str]
    stance: Literal["supports", "violates"]


class CandidateAssessment(BaseModel):
    """Evidence links for one known candidate; scores are computed in code."""

    place_id: str
    links: list[EvidenceLink]


class AssessmentBatch(BaseModel):
    candidates: list[CandidateAssessment]

