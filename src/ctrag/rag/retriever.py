"""Search inside Snowflake: Cortex embeds the question, filters run in SQL, then ranking.

Ranking is cosine similarity plus a small boost for exact matches on rare terms from the question
(drug codes, gene names, long drug names). Embeddings blur tokens like PLB1004 or SI-B001, and in
this domain those tokens are often the whole question.

User input only ever travels as bound parameters. The SQL text is assembled from constant fragments.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ctrag.domain import RetrievedChunk, SearchFilters, Section
from ctrag.warehouse.types import Connection

# Retrieval models in the arctic-embed family expect an instruction in front of queries only.
_QUERY_PREFIXES = {
    "snowflake-arctic-embed-m": "Represent this sentence for searching relevant passages: ",
    "snowflake-arctic-embed-l-v2.0": "query: ",
}

KEYWORD_WEIGHT = 0.04
MAX_KEYWORDS = 4
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9]")
_COMMON_WORDS = frozenset(
    {
        "trial", "trials", "study", "studies", "patients", "participants", "treatment",
        "treatments", "therapy", "therapies", "combination", "combining", "combined", "compared",
        "compares", "comparing", "previously", "chemotherapy", "evaluates", "evaluating",
        "recruiting", "currently", "outcome", "outcomes", "disease", "advanced", "metastatic",
        "non-small", "anyone", "measure", "formulation",
    }
)  # fmt: skip

_SEARCH_SQL = """
WITH query AS (
    SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_768(%(embed_model)s, %(query_text)s) AS embedding
)
SELECT
    c.chunk_id,
    c.nct_id,
    c.section,
    c.chunk_text,
    s.brief_title,
    s.phase_label,
    s.overall_status,
    VECTOR_COSINE_SIMILARITY(c.embedding, query.embedding) + {keyword_score} AS score
FROM RAG.CHUNKS c
JOIN CORE.STUDIES s ON s.nct_id = c.nct_id
CROSS JOIN query
{where}
ORDER BY score DESC
LIMIT %(top_k)s
"""


@dataclass(frozen=True, slots=True)
class SqlQuery:
    text: str
    params: dict[str, object]


def query_text_for(embed_model: str, question: str) -> str:
    for family, prefix in _QUERY_PREFIXES.items():
        if embed_model.startswith(family):
            return prefix + question
    return question


def distinctive_terms(question: str) -> tuple[str, ...]:
    """Tokens worth an exact match: codes with digits or hyphens, acronyms, long names."""
    terms: list[str] = []
    for token in _TOKEN.findall(question):
        lowered = token.lower()
        if lowered in _COMMON_WORDS or lowered in (t.lower() for t in terms):
            continue
        is_code = any(ch.isdigit() for ch in token) or "-" in token
        is_acronym = token.isupper() and len(token) >= 3
        if is_code or is_acronym or len(token) >= 9:
            terms.append(token)
    return tuple(terms[:MAX_KEYWORDS])


def _bind_list(params: dict[str, object], prefix: str, values: Sequence[str]) -> str:
    names = []
    for index, value in enumerate(values):
        key = f"{prefix}_{index}"
        params[key] = value
        names.append(f"%({key})s")
    return ", ".join(names)


def build_search_query(
    question: str,
    filters: SearchFilters,
    *,
    embed_model: str,
    top_k: int,
    query_prefix: bool = True,
    keyword_boost: bool = True,
) -> SqlQuery:
    params: dict[str, object] = {
        "embed_model": embed_model,
        "query_text": query_text_for(embed_model, question) if query_prefix else question,
        "top_k": top_k,
    }
    clauses: list[str] = []
    if filters.phases:
        bound = _bind_list(params, "phase", sorted(p.value for p in filters.phases))
        clauses.append(f"ARRAYS_OVERLAP(c.phases, ARRAY_CONSTRUCT({bound}))")
    if filters.statuses:
        bound = _bind_list(params, "status", sorted(s.value for s in filters.statuses))
        clauses.append(f"c.overall_status IN ({bound})")
    if filters.sections:
        bound = _bind_list(params, "section", sorted(s.value for s in filters.sections))
        clauses.append(f"c.section IN ({bound})")
    if filters.condition:
        params["condition"] = f"%{filters.condition.strip()}%"
        clauses.append("ARRAY_TO_STRING(c.conditions, ' | ') ILIKE %(condition)s")

    boosts = []
    for index, term in enumerate(distinctive_terms(question) if keyword_boost else ()):
        params[f"term_{index}"] = f"%{term}%"
        boosts.append(f"IFF(c.chunk_text ILIKE %(term_{index})s, {KEYWORD_WEIGHT}, 0)")
    keyword_score = f"({' + '.join(boosts)})" if boosts else "0"

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    text = _SEARCH_SQL.format(where=where, keyword_score=keyword_score)
    return SqlQuery(text=text, params=params)


def _to_chunk(row: Sequence[Any]) -> RetrievedChunk:
    chunk_id, nct_id, section, text, title, phase_label, status, score = row
    return RetrievedChunk(
        chunk_id=str(chunk_id),
        nct_id=str(nct_id),
        section=Section(section),
        text=str(text),
        title=str(title),
        phase_label=str(phase_label) if phase_label else "not applicable",
        status=str(status),
        score=float(score),
    )


class SnowflakeRetriever:
    def __init__(
        self,
        conn: Connection,
        *,
        embed_model: str,
        query_prefix: bool = True,
        keyword_boost: bool = True,
    ) -> None:
        self._conn = conn
        self._embed_model = embed_model
        self._query_prefix = query_prefix
        self._keyword_boost = keyword_boost

    def search(self, question: str, filters: SearchFilters, top_k: int) -> list[RetrievedChunk]:
        query = build_search_query(
            question,
            filters,
            embed_model=self._embed_model,
            top_k=top_k,
            query_prefix=self._query_prefix,
            keyword_boost=self._keyword_boost,
        )
        cursor = self._conn.cursor()
        try:
            cursor.execute(query.text, query.params)
            rows = cursor.fetchall()
        finally:
            cursor.close()
        return [_to_chunk(row) for row in rows]
