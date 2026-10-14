import pytest

from ctrag.domain import Phase, SearchFilters, TrialStatus
from ctrag.rag.filters import effective_filters, infer_filters


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Which Phase 3 trials test osimertinib?", {Phase.PHASE3}),
        ("phase III efficacy endpoints", {Phase.PHASE3}),
        ("Phase I dose escalation of KRAS inhibitors", {Phase.PHASE1}),
        ("phase IV safety follow-up", {Phase.PHASE4}),
        ("Phase 1/2 studies of ADCs", {Phase.PHASE1, Phase.PHASE2}),
        ("phase 2 and phase 3 trials", {Phase.PHASE2, Phase.PHASE3}),
        ("early phase 1 studies", {Phase.EARLY_PHASE1}),
        ("What endpoints do immunotherapy trials use?", set()),
        ("which phase is most common?", set()),
    ],
)
def test_phase_mentions_become_filters(question: str, expected: set[Phase]) -> None:
    assert infer_filters(question).phases == frozenset(expected)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Which trials are recruiting in Germany?", {TrialStatus.RECRUITING}),
        ("trials not yet recruiting", {TrialStatus.NOT_YET_RECRUITING}),
        ("completed trials with results", {TrialStatus.COMPLETED}),
        ("trials of pembrolizumab", set()),
    ],
)
def test_status_mentions_become_filters(question: str, expected: set[TrialStatus]) -> None:
    assert infer_filters(question).statuses == frozenset(expected)


def test_explicit_filters_win_over_inferred() -> None:
    explicit = SearchFilters(phases=frozenset({Phase.PHASE2}))
    applied = effective_filters("Phase 3 recruiting trials", explicit)
    assert applied.phases == frozenset({Phase.PHASE2})
    assert applied.statuses == frozenset({TrialStatus.RECRUITING})
