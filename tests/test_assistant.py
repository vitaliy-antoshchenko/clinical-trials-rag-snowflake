from collections.abc import Sequence

from ctrag.domain import (
    Answer,
    ChatMessage,
    CitationStatus,
    Completion,
    Phase,
    RetrievedChunk,
    SearchFilters,
)
from ctrag.rag.assistant import NO_RECORDS_MESSAGE, TrialAssistant
from tests.conftest import make_chunk


class StubRetriever:
    def __init__(self, chunks: Sequence[RetrievedChunk]) -> None:
        self.chunks = list(chunks)
        self.calls: list[tuple[str, SearchFilters, int]] = []

    def search(self, question: str, filters: SearchFilters, top_k: int) -> list[RetrievedChunk]:
        self.calls.append((question, filters, top_k))
        return self.chunks


class StubGenerator:
    def __init__(self, text: str) -> None:
        self.text = text
        self.messages: list[Sequence[ChatMessage]] = []

    def complete(self, messages: Sequence[ChatMessage]) -> Completion:
        self.messages.append(messages)
        return Completion(text=self.text, model="stub", prompt_tokens=10, completion_tokens=5)


class MemoryAuditLog:
    def __init__(self) -> None:
        self.answers: list[Answer] = []

    def record(self, answer: Answer) -> None:
        self.answers.append(answer)


def test_answer_is_generated_checked_and_logged() -> None:
    retriever = StubRetriever([make_chunk("NCT00000001"), make_chunk("NCT00000002")])
    generator = StubGenerator("Drug A is compared with docetaxel in this trial [NCT00000001].")
    audit = MemoryAuditLog()

    answer = TrialAssistant(retriever, generator, audit, top_k=4).ask(
        "  Which Phase 3 trials compare drug A with docetaxel?  "
    )

    assert retriever.calls[0][1].phases == frozenset({Phase.PHASE3})
    assert retriever.calls[0][2] == 4
    assert "NCT00000002" in generator.messages[0][1].content
    assert answer.citations.status is CitationStatus.OK
    assert answer.model == "stub"
    assert audit.answers == [answer]


def test_no_records_skips_the_model_but_is_still_logged() -> None:
    generator = StubGenerator("unused")
    audit = MemoryAuditLog()

    answer = TrialAssistant(StubRetriever([]), generator, audit, top_k=4).ask("anything")

    assert answer.text == NO_RECORDS_MESSAGE
    assert generator.messages == []
    assert audit.answers == [answer]


def test_invented_citation_is_reported_on_the_answer() -> None:
    retriever = StubRetriever([make_chunk("NCT00000001")])
    generator = StubGenerator("The trial enrols EGFR-mutant patients [NCT12345678].")

    answer = TrialAssistant(retriever, generator, MemoryAuditLog(), top_k=4).ask("EGFR trials?")

    assert answer.citations.status is CitationStatus.UNSUPPORTED_CITATIONS
    assert answer.citations.unsupported == ("NCT12345678",)
