"""Key-pair authenticated connection for a Snowflake service user (no passwords, no MFA prompts)."""

from __future__ import annotations

from collections.abc import Iterable

import snowflake.connector
from snowflake.connector import SnowflakeConnection

from ctrag.config import SnowflakeSettings
from ctrag.errors import ConfigError
from ctrag.warehouse.types import Connection, Cursor

QUERY_TAG = "clinical-trials-rag"


class SnowflakeSession:
    """Adapts the connector to the narrow Connection protocol the rest of the code depends on."""

    def __init__(self, raw: SnowflakeConnection) -> None:
        self._raw = raw

    def cursor(self) -> Cursor:
        return self._raw.cursor()

    def execute_string(self, sql_text: str) -> Iterable[Cursor]:
        return self._raw.execute_string(sql_text)

    def close(self) -> None:
        self._raw.close()


def connect(settings: SnowflakeSettings) -> Connection:
    key_path = settings.private_key_path
    if not key_path.is_file():
        raise ConfigError(f"Private key not found at {key_path} (SNOWFLAKE_PRIVATE_KEY_PATH)")
    raw = snowflake.connector.connect(
        account=settings.account,
        user=settings.user,
        authenticator="SNOWFLAKE_JWT",
        private_key_file=str(key_path),
        role=settings.role,
        warehouse=settings.warehouse,
        database=settings.database,
        session_parameters={"QUERY_TAG": QUERY_TAG},
    )
    return SnowflakeSession(raw)
