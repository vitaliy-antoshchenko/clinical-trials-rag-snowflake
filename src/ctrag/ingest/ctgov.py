"""ClinicalTrials.gov API v2 client.

Records are kept exactly as the API returns them and land in a VARIANT column. All parsing happens
later, in SQL inside Snowflake, so the raw layer can always be replayed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from ctrag import __version__
from ctrag.domain import Phase
from ctrag.errors import IngestError

logger = logging.getLogger(__name__)

API_URL = "https://clinicaltrials.gov/api/v2/studies"
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class StudyQuery:
    """One therapeutic-area slice of interventional trials."""

    condition: str
    started_on_or_after: date
    phases: tuple[Phase, ...]
    max_studies: int

    def to_params(self) -> dict[str, str]:
        clauses = [
            "AREA[StudyType]INTERVENTIONAL",
            f"AREA[StartDate]RANGE[{self.started_on_or_after.isoformat()},MAX]",
        ]
        if self.phases:
            phase_terms = " OR ".join(f"AREA[Phase]{phase.value}" for phase in self.phases)
            clauses.append(f"({phase_terms})")
        return {
            "query.cond": self.condition,
            "filter.advanced": " AND ".join(clauses),
            "pageSize": str(min(MAX_PAGE_SIZE, self.max_studies)),
            "format": "json",
        }


@dataclass(frozen=True, slots=True)
class RawStudy:
    nct_id: str
    payload: Mapping[str, Any]


def _nct_id(record: Mapping[str, Any]) -> str:
    try:
        nct_id = record["protocolSection"]["identificationModule"]["nctId"]
    except (KeyError, TypeError) as exc:
        raise IngestError("Study record has no protocolSection.identificationModule.nctId") from exc
    if not isinstance(nct_id, str) or not nct_id.startswith("NCT"):
        raise IngestError(f"Unexpected NCT ID in study record: {nct_id!r}")
    return nct_id


class ClinicalTrialsClient:
    def __init__(self, http: httpx.Client, base_url: str = API_URL) -> None:
        self._http = http
        self._base_url = base_url

    def iter_studies(self, query: StudyQuery) -> Iterator[RawStudy]:
        base_params = query.to_params()
        fetched = 0
        page_token: str | None = None
        while fetched < query.max_studies:
            params = dict(base_params)
            if page_token:
                params["pageToken"] = page_token
            response = self._http.get(self._base_url, params=params)
            response.raise_for_status()
            body = response.json()
            studies = body.get("studies") or []
            logger.info("Fetched page with %d studies", len(studies))
            for record in studies:
                if fetched >= query.max_studies:
                    return
                yield RawStudy(nct_id=_nct_id(record), payload=record)
                fetched += 1
            page_token = body.get("nextPageToken")
            if not page_token or not studies:
                return


def write_jsonl(studies: Iterable[RawStudy], path: Path) -> int:
    """Write one raw record per line, the format Snowflake's COPY INTO expects for JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for study in studies:
            handle.write(json.dumps(study.payload, ensure_ascii=False))
            handle.write("\n")
            count += 1
    return count


def default_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0),
        transport=httpx.HTTPTransport(retries=3),
        headers={"User-Agent": f"clinical-trials-rag-snowflake/{__version__}"},
    )
