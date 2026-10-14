from pathlib import Path

import pytest

from ctrag.domain import Phase, RetrievedChunk, SearchFilters
from ctrag.errors import ConfigError
from ctrag.evaluation.cases import EvalCase, load_cases
from ctrag.evaluation.metrics import (
    evaluate_retrieval,
    first_hit_rank,
    rank_trials,
    summarize_retrieval,
)
from tests.conftest import make_chunk


def test_chunks_collapse_to_ranked_trials() -> None:
    chunks = [make_chunk("NCT1"), make_chunk("NCT2"), make_chunk("NCT1"), make_chunk("NCT3")]
    assert rank_trials(chunks) == ("NCT1", "NCT2", "NCT3")


def test_first_hit_rank() -> None:
    assert first_hit_rank(("A", "B", "C"), frozenset({"C", "Z"})) == 3
    assert first_hit_rank(("A", "B"), frozenset({"Z"})) is None


class OrderedRetriever:
    def __init__(self, by_question: dict[str, list[str]]) -> None:
        self.by_question = by_question
        self.filters: list[SearchFilters] = []

    def search(self, question: str, filters: SearchFilters, top_k: int) -> list[RetrievedChunk]:
        self.filters.append(filters)
        return [make_chunk(n) for n in self.by_question[question]][:top_k]


def test_hit_rate_and_mrr() -> None:
    cases = [
        EvalCase("q1", "first", frozenset({"NCT1"})),
        EvalCase("q2", "second", frozenset({"NCT9"})),
        EvalCase("q3", "Phase 3 third", frozenset({"NCT5"})),
    ]
    retriever = OrderedRetriever(
        {"first": ["NCT1", "NCT2"], "second": ["NCT2", "NCT3"], "Phase 3 third": ["NCT4", "NCT5"]}
    )
    results = evaluate_retrieval(retriever, cases, chunk_pool=10)
    summary = summarize_retrieval(results, k=5)

    assert [r.first_hit for r in results] == [1, None, 2]
    assert summary.hit_rate == pytest.approx(2 / 3)
    assert summary.mrr == pytest.approx((1 + 0.5) / 3)
    assert retriever.filters[2].phases == frozenset({Phase.PHASE3})


def test_cases_file_is_validated(tmp_path: Path) -> None:
    good = tmp_path / "good.jsonl"
    good.write_text(
        '{"id": "c1", "question": "Q?", '
        '"expected_nct_ids": ["NCT01234567"], "phases": ["PHASE2"]}\n'
    )
    (case,) = load_cases(good)
    assert case.expected == frozenset({"NCT01234567"})
    assert case.filters.phases == frozenset({Phase.PHASE2})

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "c1", "question": "Q?", "expected_nct_ids": ["123"]}\n')
    with pytest.raises(ConfigError):
        load_cases(bad)


def test_shipped_cases_file_is_valid() -> None:
    cases = load_cases(Path(__file__).parents[1] / "eval" / "cases.jsonl")
    assert len(cases) >= 10
    assert len({c.case_id for c in cases}) == len(cases)
