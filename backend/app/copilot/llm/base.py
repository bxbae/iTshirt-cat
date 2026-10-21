"""LLM provider interface.

Every pipeline step asks for a JSON object for a named task. The real provider sends
`system` + `user` to the model; the mock provider ignores the prompts and builds a
deterministic answer from `context`, so the whole app and its tests run offline.
"""
import json
import re
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def complete_json(self, task: str, system: str, user: str, context: dict[str, Any]) -> dict[str, Any]:
        ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_object(raw: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply, tolerating code fences and extra prose."""
    text = _FENCE.sub("", raw.strip())
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start : i + 1])
                        if isinstance(value, dict):
                            return value
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise LLMError(f"Model reply did not contain a JSON object: {raw[:200]!r}")
