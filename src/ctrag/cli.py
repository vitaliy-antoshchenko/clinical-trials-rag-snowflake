"""Command line: fetch, build, ask, eval, doctor."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from snowflake.connector.errors import Error as SnowflakeError

from ctrag.config import Settings, load_settings
from ctrag.domain import Phase, SearchFilters, Section, TrialStatus
from ctrag.errors import CtragError
from ctrag.evaluation.cases import EvalCase, load_cases
from ctrag.evaluation.metrics import (
    RetrievalSummary,
    evaluate_generation,
    evaluate_retrieval,
    summarize_generation,
    summarize_retrieval,
)
from ctrag.ingest.ctgov import ClinicalTrialsClient, StudyQuery, default_http_client, write_jsonl
from ctrag.output import (
    render_ablation,
    render_answer,
    render_checks,
    render_counts,
    render_generation,
    render_retrieval,
)
from ctrag.rag.assistant import TrialAssistant
from ctrag.rag.audit import DisabledAuditLog, SnowflakeAuditLog
from ctrag.rag.generator import CortexGenerator
from ctrag.rag.retriever import SnowflakeRetriever
from ctrag.warehouse.build import build_warehouse
from ctrag.warehouse.connection import connect
from ctrag.warehouse.doctor import run_checks
from ctrag.warehouse.types import Connection

DEFAULT_RAW_FILE = Path("data/raw/ctgov_studies.jsonl")
DEFAULT_CASES_FILE = Path("eval/cases.jsonl")


@contextmanager
def _session(settings: Settings) -> Iterator[Connection]:
    conn = connect(settings.snowflake)
    try:
        yield conn
    finally:
        conn.close()


def _phases(raw: str) -> tuple[Phase, ...]:
    return tuple(Phase(part.strip().upper()) for part in raw.split(",") if part.strip())


def _explicit_filters(args: argparse.Namespace) -> SearchFilters:
    return SearchFilters(
        phases=frozenset(Phase(p) for p in args.phase or []),
        statuses=frozenset(TrialStatus(s) for s in args.status or []),
        sections=frozenset(Section(s) for s in args.section or []),
        condition=args.condition,
    )


def cmd_fetch(args: argparse.Namespace) -> int:
    query = StudyQuery(
        condition=args.condition,
        started_on_or_after=args.since,
        phases=args.phases,
        max_studies=args.max,
    )
    with default_http_client() as http:
        count = write_jsonl(ClinicalTrialsClient(http).iter_studies(query), args.out)
    print(f"Saved {count} studies to {args.out}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    settings = load_settings()
    with _session(settings) as conn:
        counts = build_warehouse(conn, args.input, embed_model=settings.embed_model)
    print("Build complete. Rows per layer:")
    print(render_counts(counts))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    settings = load_settings()
    with _session(settings) as conn:
        assistant = TrialAssistant(
            SnowflakeRetriever(conn, embed_model=settings.embed_model),
            CortexGenerator(conn, model=settings.llm_model),
            SnowflakeAuditLog(conn),
            top_k=args.top_k or settings.top_k,
        )
        answer = assistant.ask(args.question, _explicit_filters(args))
    print(render_answer(answer, show_context=args.show_context))
    return 0


# Retrieval variants for `ctrag eval --ablation`: what each ranking step adds.
ABLATION = (
    ("vector only", {"query_prefix": False, "keyword_boost": False}),
    ("+ query instruction", {"query_prefix": True, "keyword_boost": False}),
    ("+ keyword boost (default)", {"query_prefix": True, "keyword_boost": True}),
)


def _run_ablation(
    conn: Connection, embed_model: str, cases: Sequence[EvalCase], *, k: int, pool: int
) -> list[tuple[str, RetrievalSummary]]:
    rows = []
    for name, options in ABLATION:
        retriever = SnowflakeRetriever(conn, embed_model=embed_model, **options)
        results = evaluate_retrieval(retriever, cases, chunk_pool=pool)
        rows.append((name, summarize_retrieval(results, k=k)))
    return rows


def cmd_eval(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    settings = load_settings()
    with _session(settings) as conn:
        if args.ablation:
            rows = _run_ablation(conn, settings.embed_model, cases, k=args.k, pool=args.pool)
            print(render_ablation(rows))
            return 0
        retriever = SnowflakeRetriever(conn, embed_model=settings.embed_model)
        retrieval = evaluate_retrieval(retriever, cases, chunk_pool=args.pool)
        print(render_retrieval(retrieval, summarize_retrieval(retrieval, k=args.k)))
        if args.generate:
            assistant = TrialAssistant(
                retriever,
                CortexGenerator(conn, model=settings.llm_model),
                DisabledAuditLog(),
                top_k=settings.top_k,
            )
            generation = evaluate_generation(assistant, cases)
            print()
            print(render_generation(generation, summarize_generation(generation)))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    del args
    settings = load_settings()
    with _session(settings) as conn:
        checks = run_checks(conn, embed_model=settings.embed_model, llm_model=settings.llm_model)
    print(render_checks(checks))
    return 0 if all(c.ok for c in checks) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ctrag", description="Clinical-trials AI assistant on Snowflake."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log progress to stderr")
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="download a trial slice from ClinicalTrials.gov")
    fetch.add_argument("--condition", default="non-small cell lung cancer")
    fetch.add_argument("--since", type=date.fromisoformat, default=date(2019, 1, 1))
    fetch.add_argument("--phases", type=_phases, default=(Phase.PHASE1, Phase.PHASE2, Phase.PHASE3))
    fetch.add_argument("--max", type=int, default=500)
    fetch.add_argument("--out", type=Path, default=DEFAULT_RAW_FILE)
    fetch.set_defaults(handler=cmd_fetch)

    build = commands.add_parser("build", help="load raw records and build CORE and RAG layers")
    build.add_argument("--input", type=Path, default=DEFAULT_RAW_FILE)
    build.set_defaults(handler=cmd_build)

    ask = commands.add_parser("ask", help="ask a question, get a cited answer")
    ask.add_argument("question")
    ask.add_argument("--phase", action="append", choices=[p.value for p in Phase])
    ask.add_argument("--status", action="append", choices=[s.value for s in TrialStatus])
    ask.add_argument("--section", action="append", choices=[s.value for s in Section])
    ask.add_argument("--condition", help="substring match on reported or MeSH conditions")
    ask.add_argument("--top-k", type=int)
    ask.add_argument(
        "--show-context", action="store_true", help="print the chunks sent to the model"
    )
    ask.set_defaults(handler=cmd_ask)

    evaluate = commands.add_parser("eval", help="run the evaluation question set")
    evaluate.add_argument("--cases", type=Path, default=DEFAULT_CASES_FILE)
    evaluate.add_argument("--k", type=int, default=5, help="trial-level cutoff for hit rate")
    evaluate.add_argument("--pool", type=int, default=30, help="chunks retrieved per question")
    evaluate.add_argument("--generate", action="store_true", help="also generate and check answers")
    evaluate.add_argument(
        "--ablation", action="store_true", help="compare retrieval with ranking steps switched off"
    )
    evaluate.set_defaults(handler=cmd_eval)

    doctor = commands.add_parser("doctor", help="check connection, Cortex access and row counts")
    doctor.set_defaults(handler=cmd_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    handler: Callable[[argparse.Namespace], int] = args.handler
    try:
        return handler(args)
    except CtragError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except SnowflakeError as exc:
        print(f"snowflake error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
