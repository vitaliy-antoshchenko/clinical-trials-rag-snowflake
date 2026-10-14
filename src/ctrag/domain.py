"""Typed, immutable models shared by every layer. Values mirror ClinicalTrials.gov API v2 enums."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Phase(StrEnum):
    EARLY_PHASE1 = "EARLY_PHASE1"
    PHASE1 = "PHASE1"
    PHASE2 = "PHASE2"
    PHASE3 = "PHASE3"
    PHASE4 = "PHASE4"


class TrialStatus(StrEnum):
    NOT_YET_RECRUITING = "NOT_YET_RECRUITING"
    RECRUITING = "RECRUITING"
    ENROLLING_BY_INVITATION = "ENROLLING_BY_INVITATION"
    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    COMPLETED = "COMPLETED"
    WITHDRAWN = "WITHDRAWN"
    UNKNOWN = "UNKNOWN"


class Section(StrEnum):
    """Retrieval sections. Each trial is split by meaning first, then by length."""

    OVERVIEW = "overview"
    TREATMENT = "treatment"
    ELIGIBILITY_INCLUSION = "eligibility_inclusion"
    ELIGIBILITY_EXCLUSION = "eligibility_exclusion"
    OUTCOMES = "outcomes"


@dataclass(frozen=True, slots=True)
class SearchFilters:
    """Hard filters applied in SQL before vector ranking, so phases and statuses never mix."""

    phases: frozenset[Phase] = frozenset()
    statuses: frozenset[TrialStatus] = frozenset()
    sections: frozenset[Section] = frozenset()
    condition: str | None = None

    def merged_with(self, override: SearchFilters) -> SearchFilters:
        """Fields set on `override` win; empty fields fall back to this instance."""
        return SearchFilters(
            phases=override.phases or self.phases,
            statuses=override.statuses or self.statuses,
            sections=override.sections or self.sections,
            condition=override.condition or self.condition,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "phases": sorted(p.value for p in self.phases),
            "statuses": sorted(s.value for s in self.statuses),
            "sections": sorted(s.value for s in self.sections),
            "condition": self.condition,
        }


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: str
    nct_id: str
    section: Section
    text: str
    title: str
    phase_label: str
    status: str
    score: float


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class CitationStatus(StrEnum):
    OK = "ok"
    UNCITED_CLAIMS = "uncited_claims"
    UNSUPPORTED_CITATIONS = "unsupported_citations"


@dataclass(frozen=True, slots=True)
class CitationReport:
    """Result of checking an answer against the records it was given."""

    cited: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    uncited_sentences: tuple[str, ...] = ()

    @property
    def status(self) -> CitationStatus:
        if self.unsupported:
            return CitationStatus.UNSUPPORTED_CITATIONS
        if self.uncited_sentences:
            return CitationStatus.UNCITED_CLAIMS
        return CitationStatus.OK


@dataclass(frozen=True, slots=True)
class Answer:
    question: str
    text: str
    filters: SearchFilters
    sources: tuple[RetrievedChunk, ...]
    citations: CitationReport
    completion: Completion | None = None

    @property
    def model(self) -> str | None:
        return self.completion.model if self.completion else None

    def source_trials(self) -> tuple[RetrievedChunk, ...]:
        """One chunk per trial, in retrieval order, for display."""
        seen: set[str] = set()
        unique: list[RetrievedChunk] = []
        for chunk in self.sources:
            if chunk.nct_id not in seen:
                seen.add(chunk.nct_id)
                unique.append(chunk)
        return tuple(unique)
