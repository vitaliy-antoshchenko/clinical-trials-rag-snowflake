"""Prompt for grounded, cited answers. The rules are also checked in code (rag/citations.py)."""

from __future__ import annotations

from collections.abc import Sequence

from ctrag.domain import ChatMessage, RetrievedChunk

SYSTEM_PROMPT = """\
You are a research assistant for clinical trial teams. Answer only from the trial registry \
records in the user message.

Rules:
1. End every factual sentence with the ID of the record that supports it, in square brackets, \
for example [NCT01234567]. This includes each line of a list about the same trial. Use only IDs \
that appear in the records.
2. If the records do not answer the question, say that plainly. Do not fill gaps with outside \
knowledge.
3. Keep phases apart. Say which phase a finding comes from. Never combine safety findings from \
early-phase trials with efficacy findings from late-phase trials.
4. Registry text describes what a trial plans or reports. Do not present it as medical advice or \
as proof that a treatment works.
5. Be brief: a short paragraph or a short list, about 150 words at most."""


def format_record(chunk: RetrievedChunk) -> str:
    return (
        f'<record id="{chunk.nct_id}" phase="{chunk.phase_label}" status="{chunk.status}" '
        f'section="{chunk.section.value}">\n{chunk.text}\n</record>'
    )


def build_messages(question: str, chunks: Sequence[RetrievedChunk]) -> tuple[ChatMessage, ...]:
    records = "\n\n".join(format_record(chunk) for chunk in chunks)
    user = f"Question: {question}\n\nTrial records:\n{records}"
    return (
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user),
    )
