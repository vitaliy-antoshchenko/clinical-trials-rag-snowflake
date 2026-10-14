"""Settings come from the environment or a local .env file. Nothing is hardcoded."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ctrag.errors import ConfigError

DEFAULT_EMBED_MODEL = "snowflake-arctic-embed-m-v1.5"
DEFAULT_LLM_MODEL = "claude-sonnet-5-5"
DEFAULT_TOP_K = 8
MAX_TOP_K = 50


@dataclass(frozen=True, slots=True)
class SnowflakeSettings:
    account: str
    user: str
    private_key_path: Path
    role: str
    warehouse: str
    database: str


@dataclass(frozen=True, slots=True)
class Settings:
    snowflake: SnowflakeSettings
    embed_model: str
    llm_model: str
    top_k: int


def _require(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable {key} (see .env.example)")
    return value


def _optional(env: Mapping[str, str], key: str, default: str) -> str:
    return env.get(key, "").strip() or default


def _parse_top_k(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"CTRAG_TOP_K must be an integer, got {raw!r}") from exc
    if not 1 <= value <= MAX_TOP_K:
        raise ConfigError(f"CTRAG_TOP_K must be between 1 and {MAX_TOP_K}, got {value}")
    return value


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source: Mapping[str, str] = os.environ if env is None else env
    return Settings(
        snowflake=SnowflakeSettings(
            account=_require(source, "SNOWFLAKE_ACCOUNT"),
            user=_require(source, "SNOWFLAKE_USER"),
            private_key_path=Path(_require(source, "SNOWFLAKE_PRIVATE_KEY_PATH")).expanduser(),
            role=_optional(source, "SNOWFLAKE_ROLE", "CTRAG_ROLE"),
            warehouse=_optional(source, "SNOWFLAKE_WAREHOUSE", "CTRAG_WH"),
            database=_optional(source, "SNOWFLAKE_DATABASE", "CTRAG"),
        ),
        embed_model=_optional(source, "CTRAG_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        llm_model=_optional(source, "CTRAG_LLM_MODEL", DEFAULT_LLM_MODEL),
        top_k=_parse_top_k(_optional(source, "CTRAG_TOP_K", str(DEFAULT_TOP_K))),
    )
