"""Claude provider.

Request shape follows the Claude 5.5-family rules (platform.claude.com model migration guides):
  - no temperature / top_p / top_k: non-default values return 400 on these models
  - adaptive thinking is always on and counts toward max_tokens, so limits leave room for it
  - output_config.effort keeps thinking short for these small JSON tasks (env ANTHROPIC_EFFORT)
Sent through extra_body so it does not depend on the SDK version's typed fields.
"""
import os
import time
from typing import Any

from .base import LLMError, parse_json_object

# Room for adaptive thinking plus the JSON answer.
MAX_TOKENS = {"analyze": 4000, "drafts": 8000, "summary": 4000}


def _api_message(exc) -> str:
    """The API's own error type and message, without the request body."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") or {}
        if isinstance(err, dict) and err.get("message"):
            return f"{err.get('type', 'error')}: {err['message']}"[:300]
    return str(getattr(exc, "message", exc))[:300]


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set (or use LLM_PROVIDER=mock)")
        import anthropic  # imported lazily so the mock mode needs no SDK

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=90)
        self.model = model
        self.effort = os.getenv("ANTHROPIC_EFFORT", "low").strip()
        # Running totals for evaluation reports: tokens, calls, latency, stop reasons per task.
        self.usage: dict[str, dict[str, Any]] = {}

    def _record(self, task: str, response, seconds: float) -> None:
        u = self.usage.setdefault(task, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": [], "stop_reasons": {}})
        u["calls"] += 1
        usage = getattr(response, "usage", None)
        u["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
        u["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
        u["seconds"].append(round(seconds, 3))
        reason = getattr(response, "stop_reason", None) or "unknown"
        u["stop_reasons"][reason] = u["stop_reasons"].get(reason, 0) + 1

    def complete_json(self, task: str, system: str, user: str, context: dict[str, Any]) -> dict[str, Any]:
        extra_body = {"output_config": {"effort": self.effort}} if self.effort else None
        last_error: Exception | None = None
        for attempt in range(2):
            prompt = user if attempt == 0 else user + "\n\nReturn ONLY one valid JSON object, no prose."
            start = time.perf_counter()
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=MAX_TOKENS.get(task, 4000) * (2 if attempt else 1),
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    extra_body=extra_body,
                )
            except self._anthropic.APIStatusError as exc:
                raise LLMError(f"{task}: HTTP {exc.status_code} {_api_message(exc)}") from exc
            except self._anthropic.APIError as exc:  # connection errors, timeouts
                raise LLMError(f"{task}: {type(exc).__name__}: {exc}") from exc
            self._record(task, response, time.perf_counter() - start)
            if response.stop_reason == "refusal":
                raise LLMError(f"{task}: model declined the request")
            # Thinking blocks come first (empty by default); only text blocks carry the answer.
            raw = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
            if response.stop_reason == "max_tokens":
                last_error = LLMError(f"{task}: output hit max_tokens")
                continue  # retry once with double the limit
            try:
                return parse_json_object(raw)
            except LLMError as exc:
                last_error = exc
        raise LLMError(f"{task}: {last_error}")
