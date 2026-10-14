"""The assistant: filter, retrieve, generate, check citations, log. Each step is swappable."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ctrag.domain import (
    Answer,
    ChatMessage,
    CitationReport,
    Completion,
    RetrievedChunk,
    SearchFilters,
)
from ctrag.rag.citations import check_citations
from ctrag.rag.filters import effective_filters
from ctrag.rag.prompt import build_messages

NO_RECORDS_MESSAGE = (
    "No trial records matched this question with the current filters, so there is nothing to "
    "answer from. Try removing a filter or rephrasing."
)


class Retriever(Protocol):
    def search(
        self, question: str, filters: SearchFilters, top_k: int
    ) -> Sequence[RetrievedChunk]: ...


class Generator(Protocol):
    def complete(self, messages: Sequence[ChatMessage]) -> Completion: ...


class AuditLog(Protocol):
    def record(self, answer: Answer) -> None: ...


class TrialAssistant:
    def __init__(
        self, retriever: Retriever, generator: Generator, audit_log: AuditLog, *, top_k: int
    ) -> None:
        self._retriever = retriever
        self._generator = generator
        self._audit_log = audit_log
        self._top_k = top_k

    def ask(self, question: str, filters: SearchFilters | None = None) -> Answer:
        question = question.strip()
        if not question:
            raise ValueError("Question is empty")
        applied = effective_filters(question, filters)
        chunks = tuple(self._retriever.search(question, applied, self._top_k))
        if not chunks:
            answer = Answer(
                question=question,
                text=NO_RECORDS_MESSAGE,
                filters=applied,
                sources=(),
                citations=CitationReport(),
            )
        else:
            completion = self._generator.complete(build_messages(question, chunks))
            answer = Answer(
                question=question,
                text=completion.text,
                filters=applied,
                sources=chunks,
                citations=check_citations(completion.text, {c.nct_id for c in chunks}),
                completion=completion,
            )
        self._audit_log.record(answer)
        return answer
