"""Read hard filters out of the question itself.

"Phase 3 trials that..." should never be answered from Phase 1 records, even if the Phase 1 text is
semantically closer. So phase and recruitment status mentioned in the question become SQL filters,
not hints. Filters passed explicitly (CLI flags, API callers) always win.
"""

from __future__ import annotations

import re

from ctrag.domain import Phase, SearchFilters, TrialStatus

_NUMERAL = {"1": "1", "i": "1", "2": "2", "ii": "2", "3": "3", "iii": "3", "4": "4", "iv": "4"}
_PHASE_NUMBER = r"(iv|i{1,3}|[1-4])"
_PHASE_PATTERN = re.compile(
    rf"\bphase[\s-]*{_PHASE_NUMBER}(?:\s*(?:/|-|and|or|to)\s*(?:phase[\s-]*)?{_PHASE_NUMBER})?\b",
    re.IGNORECASE,
)
_EARLY_PHASE_PATTERN = re.compile(r"\bearly[\s-]*phase[\s-]*(?:1|i)\b", re.IGNORECASE)
_NOT_YET_RECRUITING = re.compile(r"\bnot\s+yet\s+recruiting\b", re.IGNORECASE)
_RECRUITING = re.compile(
    r"\b(?:recruiting|currently\s+enrolling|enrolling\s+now|open\s+for\s+enrol(?:l)?ment)\b",
    re.IGNORECASE,
)
_COMPLETED = re.compile(r"\bcompleted\s+(?:trials?|studies)\b", re.IGNORECASE)


def _phase(token: str) -> Phase:
    return Phase(f"PHASE{_NUMERAL[token.lower()]}")


def infer_filters(question: str) -> SearchFilters:
    phases: set[Phase] = set()
    if _EARLY_PHASE_PATTERN.search(question):
        phases.add(Phase.EARLY_PHASE1)
    without_early = _EARLY_PHASE_PATTERN.sub(" ", question)
    for match in _PHASE_PATTERN.finditer(without_early):
        phases.add(_phase(match.group(1)))
        if match.group(2):
            phases.add(_phase(match.group(2)))

    statuses: set[TrialStatus] = set()
    if _NOT_YET_RECRUITING.search(question):
        statuses.add(TrialStatus.NOT_YET_RECRUITING)
    elif _RECRUITING.search(question):
        statuses.add(TrialStatus.RECRUITING)
    if _COMPLETED.search(question):
        statuses.add(TrialStatus.COMPLETED)

    return SearchFilters(phases=frozenset(phases), statuses=frozenset(statuses))


def effective_filters(question: str, explicit: SearchFilters | None = None) -> SearchFilters:
    return infer_filters(question).merged_with(explicit or SearchFilters())
