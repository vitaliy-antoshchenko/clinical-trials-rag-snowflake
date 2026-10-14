import json

import pytest

from ctrag.domain import ChatMessage, Section
from ctrag.errors import GenerationError
from ctrag.rag.generator import CortexGenerator, parse_complete_response
from ctrag.rag.prompt import SYSTEM_PROMPT, build_messages
from tests.conftest import FakeConnection, make_chunk

CORTEX_RESPONSE = json.dumps(
    {
        "choices": [{"messages": " Answer text [NCT00000001]. "}],
        "created": 1760000000,
        "model": "claude-sonnet-5-5",
        "usage": {"completion_tokens": 12, "prompt_tokens": 900, "total_tokens": 912},
    }
)


def test_prompt_carries_every_record_with_its_phase() -> None:
    chunks = [
        make_chunk("NCT00000001", phase_label="PHASE1"),
        make_chunk("NCT00000002", section=Section.OUTCOMES, phase_label="PHASE3"),
    ]
    system, user = build_messages("Which endpoints?", chunks)

    assert system.content == SYSTEM_PROMPT
    assert user.content.startswith("Question: Which endpoints?")
    assert '<record id="NCT00000001" phase="PHASE1"' in user.content
    assert 'section="outcomes"' in user.content


def test_cortex_response_is_parsed() -> None:
    completion = parse_complete_response(CORTEX_RESPONSE, model="fallback")
    assert completion.text == "Answer text [NCT00000001]."
    assert completion.model == "claude-sonnet-5-5"
    assert completion.prompt_tokens == 900


@pytest.mark.parametrize(
    "raw", ["not json", "{}", '{"choices": []}', '{"choices": [{"messages": ""}]}']
)
def test_bad_cortex_response_raises(raw: str) -> None:
    with pytest.raises(GenerationError):
        parse_complete_response(raw, model="m")


def test_generator_sends_messages_as_bound_json() -> None:
    conn = FakeConnection(rows=[(CORTEX_RESPONSE,)])
    generator = CortexGenerator(conn, model="claude-sonnet-5-5")

    completion = generator.complete([ChatMessage(role="user", content="it's a question")])

    sql, params = conn.executed[0]
    assert params is not None
    assert "it's a question" not in sql
    assert json.loads(str(params["messages"])) == [{"role": "user", "content": "it's a question"}]
    assert json.loads(str(params["options"])) == {"max_tokens": 1500}
    assert completion.completion_tokens == 12
