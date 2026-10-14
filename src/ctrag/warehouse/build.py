"""Build pipeline: schemas, raw load (stage + COPY INTO), then SQL transforms inside Snowflake."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ctrag.errors import ConfigError
from ctrag.warehouse.sql import (
    LOAD_RAW_SCRIPT,
    SCHEMA_SCRIPT,
    TRANSFORM_SCRIPTS,
    load_script,
    render,
)
from ctrag.warehouse.types import Connection

logger = logging.getLogger(__name__)

STAGE = "@RAW.CTGOV_STAGE"

# Reported after every build, so a reviewer can see each layer is populated.
LAYER_TABLES = (
    "RAW.CTGOV_STUDIES",
    "CORE.STUDIES",
    "CORE.CONDITIONS",
    "CORE.INTERVENTIONS",
    "CORE.ARMS",
    "CORE.OUTCOMES",
    "CORE.ELIGIBILITY",
    "CORE.SITES",
    "RAG.SECTIONS",
    "RAG.CHUNKS",
)


@dataclass(frozen=True, slots=True)
class TableCount:
    table: str
    rows: int


def run_script(conn: Connection, sql_text: str) -> None:
    for cursor in conn.execute_string(sql_text):
        cursor.close()


def upload_raw_file(conn: Connection, jsonl_path: Path) -> None:
    resolved = jsonl_path.resolve()
    if not resolved.is_file():
        raise ConfigError(f"Raw file not found: {resolved}. Run `ctrag fetch` first.")
    if "'" in str(resolved):
        raise ConfigError(f"Raw file path must not contain quotes: {resolved}")
    cursor = conn.cursor()
    try:
        cursor.execute(f"REMOVE {STAGE}")
        cursor.execute(f"PUT 'file://{resolved}' {STAGE} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")
    finally:
        cursor.close()


def count_rows(conn: Connection) -> tuple[TableCount, ...]:
    cursor = conn.cursor()
    counts: list[TableCount] = []
    try:
        for table in LAYER_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 - table names are constants
            row = cursor.fetchone()
            counts.append(TableCount(table=table, rows=int(row[0]) if row else 0))
    finally:
        cursor.close()
    return tuple(counts)


def build_warehouse(
    conn: Connection, jsonl_path: Path, *, embed_model: str
) -> tuple[TableCount, ...]:
    logger.info("Creating schemas, stage and raw table")
    run_script(conn, load_script(SCHEMA_SCRIPT))
    logger.info("Uploading %s to %s", jsonl_path, STAGE)
    upload_raw_file(conn, jsonl_path)
    logger.info("Loading raw records with COPY INTO")
    run_script(conn, load_script(LOAD_RAW_SCRIPT))
    for name in TRANSFORM_SCRIPTS:
        logger.info("Running %s", name)
        run_script(conn, render(load_script(name), {"embed_model": embed_model}))
    return count_rows(conn)
