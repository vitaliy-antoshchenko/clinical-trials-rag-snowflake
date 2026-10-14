"""The small slice of the DB-API surface this project uses. Lets tests swap in fakes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol


class Cursor(Protocol):
    def execute(self, command: str, params: dict[str, object] | None = None) -> object: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> Any: ...

    def close(self) -> object: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...

    def execute_string(self, sql_text: str) -> Iterable[Cursor]: ...

    def close(self) -> object: ...
