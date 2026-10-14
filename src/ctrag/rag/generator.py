"""Answer generation with Cortex COMPLETE. Prompt and records never leave Snowflake."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from ctrag.domain import ChatMessage, Completion
from ctrag.errors import GenerationError
from ctrag.warehouse.types import Connection

_COMPLETE_SQL = (
    "SELECT SNOWFLAKE.CORTEX.COMPLETE("
    "%(model)s, PARSE_JSON(%(messages)s)::ARRAY, PARSE_JSON(%(options)s)::OBJECT)"
)


def parse_complete_response(raw: str | Mapping[str, Any], *, model: str) -> Completion:
    """Cortex returns JSON: {"choices": [{"messages": "..."}], "model": ..., "usage": {...}}."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        text = data["choices"][0]["messages"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise GenerationError(f"Unexpected Cortex COMPLETE response: {str(raw)[:300]}") from exc
    if not isinstance(text, str) or not text.strip():
        raise GenerationError("Cortex COMPLETE returned an empty answer")
    usage = data.get("usage") or {}
    return Completion(
        text=text.strip(),
        model=str(data.get("model") or model),
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
    )


class CortexGenerator:
    def __init__(
        self,
        conn: Connection,
        *,
        model: str,
        max_tokens: int = 1500,
        temperature: float | None = None,
    ) -> None:
        # Newer Claude models on Cortex reject `temperature`, so it is only sent when set.
        self._conn = conn
        self._model = model
        self._options: dict[str, float | int] = {"max_tokens": max_tokens}
        if temperature is not None:
            self._options["temperature"] = temperature

    def complete(self, messages: Sequence[ChatMessage]) -> Completion:
        params: dict[str, object] = {
            "model": self._model,
            "messages": json.dumps([{"role": m.role, "content": m.content} for m in messages]),
            "options": json.dumps(self._options),
        }
        cursor = self._conn.cursor()
        try:
            cursor.execute(_COMPLETE_SQL, params)
            row = cursor.fetchone()
        finally:
            cursor.close()
        if row is None:
            raise GenerationError("Cortex COMPLETE returned no rows")
        return parse_complete_response(row[0], model=self._model)
