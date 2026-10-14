"""Trial-level retrieval metrics and answer-level citation metrics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ctrag.domain import Answer, CitationStatus, RetrievedChunk
from ctrag.evaluation.cases import EvalCase
from ctrag.rag.assistant import Retriever, TrialAssistant
from ctrag.rag.filters import effective_filters


def rank_trials(chunks: Sequence[RetrievedChunk]) -> tuple[str, ...]:
    """Collapse ranked chunks to ranked trials, keeping the first appearance of each trial."""
    return tuple(dict.fromkeys(chunk.nct_id for chunk in chunks))


def first_hit_rank(ranked: Sequence[str], expected: frozenset[str]) -> int | None:
    for position, nct_id in enumerate(ranked, start=1):
        if nct_id in expected:
            return position
    return None


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    case: EvalCase
    ranked: tuple[str, ...]
    first_hit: int | None

    def hit_at(self, k: int) -> bool:
        return self.first_hit is not None and self.first_hit <= k


@dataclass(frozen=True, slots=True)
class RetrievalSummary:
    cases: int
    k: int
    hit_rate: float
    mrr: float


def evaluate_retrieval(
    retriever: Retriever, cases: Sequence[EvalCase], *, chunk_pool: int
) -> tuple[RetrievalResult, ...]:
    results = []
    for case in cases:
        filters = effective_filters(case.question, case.filters)
        ranked = rank_trials(retriever.search(case.question, filters, chunk_pool))
        results.append(
            RetrievalResult(
                case=case, ranked=ranked, first_hit=first_hit_rank(ranked, case.expected)
            )
        )
    return tuple(results)


def summarize_retrieval(results: Sequence[RetrievalResult], *, k: int) -> RetrievalSummary:
    if not results:
        return RetrievalSummary(cases=0, k=k, hit_rate=0.0, mrr=0.0)
    hits = sum(1 for r in results if r.hit_at(k))
    reciprocal = sum(
        1.0 / r.first_hit for r in results if r.first_hit is not None and r.first_hit <= k
    )
    return RetrievalSummary(
        cases=len(results), k=k, hit_rate=hits / len(results), mrr=reciprocal / len(results)
    )


@dataclass(frozen=True, slots=True)
class GenerationResult:
    case: EvalCase
    answer: Answer

    @property
    def expected_cited(self) -> bool:
        return bool(self.case.expected & set(self.answer.citations.cited))

    @property
    def no_invented_citations(self) -> bool:
        return not self.answer.citations.unsupported

    @property
    def fully_cited(self) -> bool:
        return self.answer.citations.status is CitationStatus.OK


@dataclass(frozen=True, slots=True)
class GenerationSummary:
    cases: int
    expected_cited_rate: float
    no_invented_citations_rate: float
    fully_cited_rate: float


def evaluate_generation(
    assistant: TrialAssistant, cases: Sequence[EvalCase]
) -> tuple[GenerationResult, ...]:
    return tuple(
        GenerationResult(case=case, answer=assistant.ask(case.question, case.filters))
        for case in cases
    )


def summarize_generation(results: Sequence[GenerationResult]) -> GenerationSummary:
    total = len(results) or 1
    return GenerationSummary(
        cases=len(results),
        expected_cited_rate=sum(r.expected_cited for r in results) / total,
        no_invented_citations_rate=sum(r.no_invented_citations for r in results) / total,
        fully_cited_rate=sum(r.fully_cited for r in results) / total,
    )
