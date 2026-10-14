"""Audit trail: each answer is stored with its filters, the chunks it saw and the check result."""

from __future__ import annotations

import json

from ctrag.domain import Answer
from ctrag.warehouse.types import Connection

_INSERT_SQL = """
INSERT INTO RAG.QA_LOG
    (asked_at, question, filters, retrieved, model, answer, citation_status, citations, usage)
SELECT
    CURRENT_TIMESTAMP(),
    %(question)s,
    PARSE_JSON(%(filters)s),
    PARSE_JSON(%(retrieved)s),
    %(model)s,
    %(answer)s,
    %(citation_status)s,
    PARSE_JSON(%(citations)s),
    PARSE_JSON(%(usage)s)
"""


def audit_params(answer: Answer) -> dict[str, object]:
    completion = answer.completion
    return {
        "question": answer.question,
        "filters": json.dumps(answer.filters.to_dict()),
        "retrieved": json.dumps(
            [{"chunk_id": c.chunk_id, "score": round(c.score, 4)} for c in answer.sources]
        ),
        "model": answer.model,
        "answer": answer.text,
        "citation_status": answer.citations.status.value,
        "citations": json.dumps(
            {
                "cited": list(answer.citations.cited),
                "unsupported": list(answer.citations.unsupported),
                "uncited_sentences": list(answer.citations.uncited_sentences),
            }
        ),
        "usage": json.dumps(
            {
                "prompt_tokens": completion.prompt_tokens if completion else 0,
                "completion_tokens": completion.completion_tokens if completion else 0,
            }
        ),
    }


class SnowflakeAuditLog:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def record(self, answer: Answer) -> None:
        cursor = self._conn.cursor()
        try:
            cursor.execute(_INSERT_SQL, audit_params(answer))
        finally:
            cursor.close()


class DisabledAuditLog:
    """For offline evaluation runs, which should not pollute the production audit log."""

    def record(self, answer: Answer) -> None:
        del answer
