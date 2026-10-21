import pytest

from app.copilot.llm.base import LLMError, parse_json_object


def test_plain_and_fenced_json():
    assert parse_json_object('{"a": 1}') == {"a": 1}
    assert parse_json_object('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}


def test_json_inside_prose_with_braces_in_strings():
    raw = 'Sure! Here it is: {"reply": "use {code}", "n": 2} Hope this helps.'
    assert parse_json_object(raw) == {"reply": "use {code}", "n": 2}


def test_no_json_raises():
    with pytest.raises(LLMError):
        parse_json_object("I cannot help with that.")
