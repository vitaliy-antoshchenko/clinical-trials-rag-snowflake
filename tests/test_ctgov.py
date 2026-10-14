import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from ctrag.domain import Phase
from ctrag.errors import IngestError
from ctrag.ingest.ctgov import ClinicalTrialsClient, StudyQuery, write_jsonl

QUERY = StudyQuery(
    condition="non-small cell lung cancer",
    started_on_or_after=date(2019, 1, 1),
    phases=(Phase.PHASE1, Phase.PHASE3),
    max_studies=3,
)


def test_query_params_express_the_slice() -> None:
    params = QUERY.to_params()
    assert params["query.cond"] == "non-small cell lung cancer"
    advanced = params["filter.advanced"]
    assert "AREA[StudyType]INTERVENTIONAL" in advanced
    assert "AREA[StartDate]RANGE[2019-01-01,MAX]" in advanced
    assert "(AREA[Phase]PHASE1 OR AREA[Phase]PHASE3)" in advanced
    assert params["pageSize"] == "3"


def _client(pages: list[dict[str, Any]], seen: list[httpx.Request]) -> ClinicalTrialsClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=pages[len(seen) - 1])

    return ClinicalTrialsClient(httpx.Client(transport=httpx.MockTransport(handler)))


def test_pagination_follows_next_page_token_and_stops_at_max(ctgov_page: dict[str, Any]) -> None:
    second_page = {"studies": ctgov_page["studies"], "nextPageToken": "MORE"}
    seen: list[httpx.Request] = []
    studies = list(_client([ctgov_page, second_page], seen).iter_studies(QUERY))

    assert len(studies) == 3
    assert studies[0].nct_id.startswith("NCT")
    assert "pageToken" not in seen[0].url.params
    assert seen[1].url.params["pageToken"] == "NEXT"


def test_stops_when_there_is_no_next_page(ctgov_page: dict[str, Any]) -> None:
    last_page = {"studies": ctgov_page["studies"][:1]}
    seen: list[httpx.Request] = []
    studies = list(_client([last_page], seen).iter_studies(QUERY))
    assert len(studies) == 1
    assert len(seen) == 1


def test_record_without_nct_id_is_rejected() -> None:
    seen: list[httpx.Request] = []
    client = _client([{"studies": [{"protocolSection": {}}]}], seen)
    with pytest.raises(IngestError):
        list(client.iter_studies(QUERY))


def test_http_errors_are_raised() -> None:
    client = ClinicalTrialsClient(
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    )
    with pytest.raises(httpx.HTTPStatusError):
        list(client.iter_studies(QUERY))


def test_write_jsonl_keeps_raw_records(ctgov_page: dict[str, Any], tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    studies = list(_client([{"studies": ctgov_page["studies"]}], seen).iter_studies(QUERY))
    out = tmp_path / "raw" / "studies.jsonl"

    assert write_jsonl(studies, out) == 2
    lines = out.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == ctgov_page["studies"][0]
