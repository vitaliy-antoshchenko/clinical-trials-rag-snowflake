"""Do not trust the model's citations, check them.

Two failure modes matter in a clinical setting:
- unsupported: the answer cites a trial that was not in the retrieved records (invented or leaked)
- uncited: a factual sentence carries no citation, so a reviewer cannot trace it
"""

from __future__ import annotations

import re
from collections.abc import Collection

from ctrag.domain import CitationReport

_NCT_ID = re.compile(r"\bNCT\d{8}\b")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")
_LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_NO_ANSWER = re.compile(
    r"\b(?:do(?:es)?\s+not|don't|doesn't)\s+(?:contain|include|mention|answer|provide|cover|"
    r"report|describe|specify|say|involve|use)\b|\bnot\s+(?:enough|sufficient)\s+information\b|"
    r"\bcannot\s+(?:answer|determine|tell|be\s+confirmed)\b|\bno\s+(?:record|trial|information)\b|"
    # Statements about the supplied records themselves, not about any trial.
    r"^(?:none\s+of\s+)?(?:the|these)\s+(?:other\s+)?(?:supplied\s+|provided\s+|retrieved\s+)?"
    r"records\b",
    re.IGNORECASE,
)
_MIN_CLAIM_LENGTH = 25


def _is_claim(sentence: str) -> bool:
    text = _LIST_MARKER.sub("", sentence).strip().strip("*_").strip()
    if len(text) < _MIN_CLAIM_LENGTH or text.endswith(":"):
        return False
    return not _NO_ANSWER.search(text)


def check_citations(answer: str, retrieved_ids: Collection[str]) -> CitationReport:
    allowed = set(retrieved_ids)
    cited = tuple(dict.fromkeys(_NCT_ID.findall(answer)))
    unsupported = tuple(nct for nct in cited if nct not in allowed)
    sentences = (s.strip() for s in _SENTENCE_BREAK.split(answer))
    uncited = tuple(s for s in sentences if s and _is_claim(s) and not _NCT_ID.search(s))
    return CitationReport(cited=cited, unsupported=unsupported, uncited_sentences=uncited)
