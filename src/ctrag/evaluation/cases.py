"""Evaluation cases: a question plus the trial IDs a correct search must surface."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ctrag.domain import Phase, SearchFilters, TrialStatus
from ctrag.errors import ConfigError

_NCT_ID = re.compile(r"^NCT\d{8}$")


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    question: str
    expected: frozenset[str]
    filters: SearchFilters = field(default_factory=SearchFilters)


def _parse_case(raw: object, line_no: int) -> EvalCase:
    if not isinstance(raw, dict):
        raise ConfigError(f"Line {line_no}: expected a JSON object")
    try:
        case_id = str(raw["id"])
        question = str(raw["question"]).strip()
        expected = frozenset(str(x) for x in raw["expected_nct_ids"])
    except KeyError as exc:
        raise ConfigError(f"Line {line_no}: missing field {exc}") from exc
    bad = [x for x in expected if not _NCT_ID.match(x)]
    if not question or not expected or bad:
        raise ConfigError(f"Line {line_no}: needs a question and valid NCT IDs (bad: {bad})")
    filters = SearchFilters(
        phases=frozenset(Phase(p) for p in raw.get("phases", [])),
        statuses=frozenset(TrialStatus(s) for s in raw.get("statuses", [])),
    )
    return EvalCase(case_id=case_id, question=question, expected=expected, filters=filters)


def load_cases(path: Path) -> tuple[EvalCase, ...]:
    if not path.is_file():
        raise ConfigError(f"Evaluation file not found: {path}")
    cases: list[EvalCase] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            cases.append(_parse_case(json.loads(line), line_no))
    if not cases:
        raise ConfigError(f"No evaluation cases in {path}")
    return tuple(cases)
