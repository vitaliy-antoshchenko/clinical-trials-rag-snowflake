"""Plain-text rendering for the CLI. Kept apart from the logic so it can change freely."""

from __future__ import annotations

from collections.abc import Sequence

from ctrag.domain import Answer, CitationStatus
from ctrag.evaluation.metrics import (
    GenerationResult,
    GenerationSummary,
    RetrievalResult,
    RetrievalSummary,
)
from ctrag.warehouse.build import TableCount
from ctrag.warehouse.doctor import Check

REGISTRY_URL = "https://clinicaltrials.gov/study/"


def _describe_filters(answer: Answer) -> str:
    applied = answer.filters.to_dict()
    parts = [
        f"{key}={','.join(v) if isinstance(v, list) else v}" for key, v in applied.items() if v
    ]
    return "; ".join(parts) if parts else "none"


def render_answer(answer: Answer, *, show_context: bool = False) -> str:
    lines = [answer.text, "", f"Filters applied: {_describe_filters(answer)}"]
    trials = answer.source_trials()
    if trials:
        lines.append("Retrieved trials:")
        for chunk in trials:
            marker = "cited" if chunk.nct_id in answer.citations.cited else "     "
            lines.append(
                f"  [{marker}] {chunk.nct_id}  {chunk.phase_label:<15} {chunk.status:<22} "
                f"{chunk.title[:70]}"
            )
            lines.append(f"           {REGISTRY_URL}{chunk.nct_id}")
    report = answer.citations
    if report.status is CitationStatus.OK:
        count = len(report.cited)
        noun = "trial" if count == 1 else "trials"
        lines.append(f"Citation check: ok ({count} {noun} cited, all retrieved)")
    else:
        lines.append(f"Citation check: {report.status.value}")
        lines.extend(f"  cited but not retrieved: {nct}" for nct in report.unsupported)
        lines.extend(f"  sentence without citation: {s}" for s in report.uncited_sentences)
    if show_context:
        lines.append("")
        lines.append("Context passed to the model:")
        for chunk in answer.sources:
            lines.append(f"--- {chunk.chunk_id} (score {chunk.score:.3f})")
            lines.append(chunk.text)
    return "\n".join(lines)


def render_counts(counts: Sequence[TableCount]) -> str:
    return "\n".join(f"  {c.table:<22} {c.rows:>8,}" for c in counts)


def render_checks(checks: Sequence[Check]) -> str:
    return "\n".join(f"  [{'ok' if c.ok else 'FAIL'}] {c.name}: {c.detail}" for c in checks)


def render_retrieval(results: Sequence[RetrievalResult], summary: RetrievalSummary) -> str:
    lines = [f"{'case':<6} {'hit rank':>8}  question"]
    for result in results:
        rank = str(result.first_hit) if result.first_hit else "-"
        lines.append(f"{result.case.case_id:<6} {rank:>8}  {result.case.question[:90]}")
    lines.append("")
    lines.append(
        f"Retrieval over {summary.cases} questions: hit@{summary.k} = {summary.hit_rate:.0%}, "
        f"MRR@{summary.k} = {summary.mrr:.2f}"
    )
    return "\n".join(lines)


def render_ablation(rows: Sequence[tuple[str, RetrievalSummary]]) -> str:
    if not rows:
        return "No ablation variants were run."
    k = rows[0][1].k
    lines = [f"{'retrieval':<28} {'hit@' + str(k):>7} {'MRR@' + str(k):>7}"]
    lines.extend(f"{name:<28} {s.hit_rate:>7.0%} {s.mrr:>7.2f}" for name, s in rows)
    return "\n".join(lines)


def render_generation(results: Sequence[GenerationResult], summary: GenerationSummary) -> str:
    lines = [f"{'case':<6} {'expected':>8} {'invented':>8} {'status':<22}"]
    for result in results:
        lines.append(
            f"{result.case.case_id:<6} {'cited' if result.expected_cited else 'missed':>8} "
            f"{'no' if result.no_invented_citations else 'YES':>8} "
            f"{result.answer.citations.status.value:<22}"
        )
    lines.append("")
    lines.append(
        f"Answers over {summary.cases} questions: "
        f"expected trial cited {summary.expected_cited_rate:.0%}, "
        f"no invented citations {summary.no_invented_citations_rate:.0%}, "
        f"every claim cited {summary.fully_cited_rate:.0%}"
    )
    return "\n".join(lines)
