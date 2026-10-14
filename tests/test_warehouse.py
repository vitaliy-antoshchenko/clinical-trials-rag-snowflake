import json
from pathlib import Path

import pytest

from ctrag.domain import Answer, CitationReport, Completion, SearchFilters
from ctrag.errors import ConfigError
from ctrag.rag.audit import SnowflakeAuditLog
from ctrag.warehouse.build import LAYER_TABLES, build_warehouse, upload_raw_file
from ctrag.warehouse.sql import TRANSFORM_SCRIPTS, load_script, render
from tests.conftest import FakeConnection, make_chunk


def test_render_inserts_safe_values_only() -> None:
    sql = "SELECT EMBED_TEXT_768('{{ embed_model }}', x)"
    assert render(sql, {"embed_model": "snowflake-arctic-embed-m-v1.5"}) == (
        "SELECT EMBED_TEXT_768('snowflake-arctic-embed-m-v1.5', x)"
    )
    with pytest.raises(ConfigError, match="Unsafe"):
        render(sql, {"embed_model": "x'); DROP TABLE t; --"})
    with pytest.raises(ConfigError, match="needs a value"):
        render(sql, {})


@pytest.mark.parametrize("name", TRANSFORM_SCRIPTS)
def test_transform_scripts_render_fully(name: str) -> None:
    rendered = render(load_script(name), {"embed_model": "model-x"})
    assert "{{" not in rendered


def test_upload_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="ctrag fetch"):
        upload_raw_file(FakeConnection(), tmp_path / "missing.jsonl")


def test_build_runs_layers_in_order(tmp_path: Path) -> None:
    raw = tmp_path / "studies.jsonl"
    raw.write_text('{"protocolSection": {}}\n')
    conn = FakeConnection(rows=[(42,)])

    counts = build_warehouse(conn, raw, embed_model="model-x")

    assert "CREATE SCHEMA IF NOT EXISTS RAW" in conn.scripts[0]
    assert "COPY INTO RAW.CTGOV_STUDIES" in conn.scripts[1]
    assert "CREATE OR REPLACE TABLE CORE.STUDIES" in conn.scripts[2]
    assert "EMBED_TEXT_768('model-x'" in conn.scripts[3]
    put = next(sql for sql, _ in conn.executed if sql.startswith("PUT"))
    assert f"file://{raw.resolve()}" in put
    assert [c.table for c in counts] == list(LAYER_TABLES)
    assert all(c.rows == 42 for c in counts)


def test_audit_log_stores_answer_with_its_evidence() -> None:
    conn = FakeConnection()
    answer = Answer(
        question="Which trials?",
        text="One trial [NCT00000001].",
        filters=SearchFilters(),
        sources=(make_chunk("NCT00000001", score=0.81234),),
        citations=CitationReport(cited=("NCT00000001",)),
        completion=Completion(text="One trial [NCT00000001].", model="m", prompt_tokens=7),
    )

    SnowflakeAuditLog(conn).record(answer)

    sql, params = conn.executed[0]
    assert "INSERT INTO RAG.QA_LOG" in sql
    assert params is not None
    assert json.loads(str(params["retrieved"])) == [
        {"chunk_id": "NCT00000001:overview:0", "score": 0.8123}
    ]
    assert params["citation_status"] == "ok"
    assert json.loads(str(params["usage"]))["prompt_tokens"] == 7
