from ctrag.domain import Phase, SearchFilters, Section, TrialStatus
from ctrag.rag.retriever import SnowflakeRetriever, build_search_query, distinctive_terms
from tests.conftest import FakeConnection


def test_no_filters_means_no_where_clause() -> None:
    query = build_search_query("q", SearchFilters(), embed_model="m", top_k=5)
    assert "WHERE" not in query.text
    assert query.params == {"embed_model": "m", "query_text": "q", "top_k": 5}


def test_filters_are_bound_not_interpolated() -> None:
    filters = SearchFilters(
        phases=frozenset({Phase.PHASE3, Phase.PHASE2}),
        statuses=frozenset({TrialStatus.RECRUITING}),
        sections=frozenset({Section.ELIGIBILITY_INCLUSION}),
        condition="EGFR",
    )
    query = build_search_query("q", filters, embed_model="m", top_k=5)

    assert "ARRAYS_OVERLAP(c.phases, ARRAY_CONSTRUCT(%(phase_0)s, %(phase_1)s))" in query.text
    assert "c.overall_status IN (%(status_0)s)" in query.text
    assert "c.section IN (%(section_0)s)" in query.text
    assert "ILIKE %(condition)s" in query.text
    assert query.params["phase_0"] == "PHASE2"
    assert query.params["phase_1"] == "PHASE3"
    assert query.params["condition"] == "%EGFR%"
    assert "PHASE3" not in query.text
    assert "EGFR" not in query.text


def test_hostile_question_only_travels_as_a_parameter() -> None:
    question = "x'); DROP TABLE RAG.CHUNKS; --"
    query = build_search_query(question, SearchFilters(), embed_model="m", top_k=5)
    assert "DROP TABLE" not in query.text
    assert query.params["query_text"] == question


def test_search_maps_rows_to_chunks() -> None:
    row = ("NCT1:overview:0", "NCT1", "overview", "text", "Title", None, "COMPLETED", 0.87)
    conn = FakeConnection(rows=[row])
    chunks = SnowflakeRetriever(conn, embed_model="m").search("q", SearchFilters(), 3)

    assert len(chunks) == 1
    assert chunks[0].section is Section.OVERVIEW
    assert chunks[0].phase_label == "not applicable"
    assert chunks[0].score == 0.87
    assert conn.executed[0][1] is not None


def test_arctic_queries_get_the_retrieval_instruction() -> None:
    query = build_search_query(
        "EGFR trials", SearchFilters(), embed_model="snowflake-arctic-embed-m-v1.5", top_k=5
    )
    assert str(query.params["query_text"]).startswith("Represent this sentence")
    plain = build_search_query(
        "EGFR trials",
        SearchFilters(),
        embed_model="snowflake-arctic-embed-m-v1.5",
        top_k=5,
        query_prefix=False,
    )
    assert plain.params["query_text"] == "EGFR trials"


def test_rare_terms_are_boosted_through_bound_parameters() -> None:
    question = "Which Phase 3 study adds SI-B001 to docetaxel in EGFR patients?"
    assert distinctive_terms(question) == ("SI-B001", "docetaxel", "EGFR")
    query = build_search_query(question, SearchFilters(), embed_model="m", top_k=5)
    assert "IFF(c.chunk_text ILIKE %(term_0)s, 0.04, 0)" in query.text
    assert query.params["term_0"] == "%SI-B001%"
    assert "SI-B001" not in query.text
    off = build_search_query(
        question, SearchFilters(), embed_model="m", top_k=5, keyword_boost=False
    )
    assert "ILIKE %(term_0)s" not in off.text
