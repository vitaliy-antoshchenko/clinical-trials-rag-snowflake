from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from ctrag.domain import RetrievedChunk, Section

FIXTURES = Path(__file__).parent / "fixtures"


class FakeCursor:
    def __init__(self, rows: Sequence[Sequence[Any]]) -> None:
        self.rows = list(rows)
        self.executed: list[tuple[str, dict[str, object] | None]] = []

    def execute(self, command: str, params: dict[str, object] | None = None) -> object:
        self.executed.append((command, params))
        return self

    def fetchone(self) -> Any:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> Any:
        return list(self.rows)

    def close(self) -> object:
        return None


class FakeConnection:
    def __init__(self, rows: Sequence[Sequence[Any]] = ()) -> None:
        self.rows = rows
        self.cursors: list[FakeCursor] = []
        self.scripts: list[str] = []

    def cursor(self) -> FakeCursor:
        cursor = FakeCursor(self.rows)
        self.cursors.append(cursor)
        return cursor

    def execute_string(self, sql_text: str) -> list[FakeCursor]:
        self.scripts.append(sql_text)
        return [FakeCursor(())]

    def close(self) -> object:
        return None

    @property
    def executed(self) -> list[tuple[str, dict[str, object] | None]]:
        return [call for cursor in self.cursors for call in cursor.executed]


def make_chunk(
    nct_id: str = "NCT00000001",
    *,
    section: Section = Section.OVERVIEW,
    score: float = 0.9,
    phase_label: str = "PHASE3",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{nct_id}:{section.value}:0",
        nct_id=nct_id,
        section=section,
        text=f"Trial {nct_id} | Example title | Phase: {phase_label}\nSome registry text.",
        title="Example title",
        phase_label=phase_label,
        status="RECRUITING",
        score=score,
    )


@pytest.fixture
def ctgov_page() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "ctgov_page.json").read_text(encoding="utf-8"))
    return data
