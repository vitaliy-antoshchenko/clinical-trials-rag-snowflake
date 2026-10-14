"""Health checks a reviewer can run first: connection, Cortex functions, layer row counts."""

from __future__ import annotations

from dataclasses import dataclass

from snowflake.connector.errors import Error as SnowflakeError

from ctrag.warehouse.build import LAYER_TABLES
from ctrag.warehouse.types import Connection


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str


def _scalar(conn: Connection, sql: str, params: dict[str, object] | None = None) -> object:
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row[0] if row else None


def _check(name: str, conn: Connection, sql: str, params: dict[str, object] | None = None) -> Check:
    try:
        value = _scalar(conn, sql, params)
    except SnowflakeError as exc:
        return Check(name=name, ok=False, detail=str(exc).splitlines()[0])
    return Check(name=name, ok=True, detail=str(value))


def run_checks(conn: Connection, *, embed_model: str, llm_model: str) -> tuple[Check, ...]:
    checks = [
        _check(
            "session",
            conn,
            "SELECT CURRENT_ACCOUNT() || ' / ' || CURRENT_ROLE() || ' / ' || CURRENT_WAREHOUSE()",
        ),
        _check(
            f"cortex embed ({embed_model})",
            conn,
            "SELECT VECTOR_COSINE_SIMILARITY(e, e) FROM "
            "(SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_768(%(model)s, 'ping') AS e)",
            {"model": embed_model},
        ),
        _check(
            f"cortex complete ({llm_model})",
            conn,
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%(model)s, 'Reply with the single word: ok')",
            {"model": llm_model},
        ),
    ]
    checks.extend(
        _check(f"rows {table}", conn, f"SELECT COUNT(*) FROM {table}")  # noqa: S608 - constant names
        for table in LAYER_TABLES
    )
    return tuple(checks)
