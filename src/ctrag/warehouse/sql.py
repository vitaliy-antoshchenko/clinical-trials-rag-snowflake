"""SQL scripts live in ctrag/sql as plain files, so they can be read and reviewed without Python.

The only templating is `{{name}}` for model names. Values are checked against a strict pattern
before they are inserted, so a template value can never close a string literal.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from importlib import resources

from ctrag.errors import ConfigError

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.\-]+$")

SCHEMA_SCRIPT = "01_schemas.sql"
LOAD_RAW_SCRIPT = "02_load_raw.sql"
TRANSFORM_SCRIPTS = ("03_core.sql", "04_rag.sql")


def load_script(name: str) -> str:
    return resources.files("ctrag.sql").joinpath(name).read_text(encoding="utf-8")


def render(sql: str, params: Mapping[str, str]) -> str:
    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            raise ConfigError(f"SQL template needs a value for {{{{{name}}}}}")
        value = params[name]
        if not _SAFE_VALUE.match(value):
            raise ConfigError(f"Unsafe value for SQL template parameter {name}: {value!r}")
        return value

    return _PLACEHOLDER.sub(substitute, sql)
