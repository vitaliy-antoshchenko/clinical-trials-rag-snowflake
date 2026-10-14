from ctrag.domain import CitationStatus
from ctrag.rag.citations import check_citations

RETRIEVED = {"NCT00000001", "NCT00000002"}


def test_fully_cited_answer_is_ok() -> None:
    answer = (
        "The Phase 3 trial compares drug A with chemotherapy [NCT00000001]. "
        "A Phase 1 study reports dose escalation in solid tumours [NCT00000002]."
    )
    report = check_citations(answer, RETRIEVED)
    assert report.status is CitationStatus.OK
    assert report.cited == ("NCT00000001", "NCT00000002")


def test_citation_outside_retrieved_records_is_flagged() -> None:
    answer = "The trial enrols EGFR-mutant patients after progression [NCT99999999]."
    report = check_citations(answer, RETRIEVED)
    assert report.status is CitationStatus.UNSUPPORTED_CITATIONS
    assert report.unsupported == ("NCT99999999",)


def test_factual_sentence_without_citation_is_flagged() -> None:
    answer = (
        "The primary endpoint is progression-free survival [NCT00000001]. "
        "Overall survival is a secondary endpoint in most of these trials."
    )
    report = check_citations(answer, RETRIEVED)
    assert report.status is CitationStatus.UNCITED_CLAIMS
    assert report.uncited_sentences == (
        "Overall survival is a secondary endpoint in most of these trials.",
    )


def test_list_items_and_no_answer_statements() -> None:
    answer = (
        "Relevant trials:\n"
        "- Drug A plus chemotherapy in first line [NCT00000001]\n"
        "- Drug B maintenance after induction therapy [NCT00000002]\n"
        "The records do not mention results for patients over 80."
    )
    report = check_citations(answer, RETRIEVED)
    assert report.status is CitationStatus.OK


def test_statements_about_the_records_are_not_claims() -> None:
    answer = (
        "None of the supplied records show a head-to-head comparison with osimertinib. "
        "The records describe combinations only [NCT00000001]."
    )
    report = check_citations(answer, RETRIEVED)
    assert report.status is CitationStatus.OK


def test_markdown_headings_are_not_claims() -> None:
    answer = "**Osimertinib-based trials without a new comparator:**\n- Drug A [NCT00000001]."
    assert check_citations(answer, RETRIEVED).status is CitationStatus.OK


def test_statements_about_other_records_are_not_claims() -> None:
    answer = (
        "One trial combines drug A with nivolumab [NCT00000001]. "
        "The other records involve nivolumab without drug A."
    )
    assert check_citations(answer, RETRIEVED).status is CitationStatus.OK
