"""Single entry point for all LLM calls in this project.

Uses Anthropic's tool-use feature with a forced `tool_choice` to enforce
structured output. The SDK validates the tool input against `input_schema`
before returning the `tool_use` block, which is more reliable than asking
the model to emit JSON in free text and parsing it ourselves.

All calls are logged as one JSON object per line to backend/logs/llm_calls.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

DEFAULT_MODEL = "claude-sonnet-4-6"
LOG_PATH = Path(__file__).parent / "logs" / "llm_calls.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_client: AsyncAnthropic | None = None


class LLMCallError(Exception):
    """Raised when an LLM call fails after retries or hits a fatal error."""


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMCallError(
                "ANTHROPIC_API_KEY is not set. Copy backend/.env.example to "
                "backend/.env and fill in a real key."
            )
        _client = AsyncAnthropic(api_key=api_key)
    return _client


def _log(entry: dict[str, Any]) -> None:
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _usage_dict(response: Any) -> dict[str, Any]:
    """Token usage for the log line, turning estimated cost into measured cost.
    Includes the prompt-cache counters (populated once the system prompt is
    cached, see E1). Returns {} when the response carries no usage."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
    }


async def llm_call(
    system_prompt: str,
    user_message: str,
    response_schema: dict[str, Any],
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """Call the LLM and return parsed structured output.

    `response_schema` is an Anthropic tool definition:
        {"name": str, "description": str, "input_schema": {...}}

    Forces the model to call this tool via `tool_choice`. Returns the tool's
    `input` dict. On a missing tool_use block, retries once with a corrective
    follow-up. Any other failure raises LLMCallError.
    """
    client = _get_client()
    tool_name = response_schema["name"]
    sys_hash = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:16]
    msg_preview = user_message[:100]
    log_full = os.environ.get("LLM_LOG_FULL") == "1"

    def _emit(entry: dict[str, Any], *, response: dict[str, Any] | None = None) -> None:
        # When LLM_LOG_FULL=1, attach the full prompts (and parsed response, if
        # any) to the log line. Default behaviour leaves the entry untouched.
        if log_full:
            entry["system_prompt"] = system_prompt
            entry["user_message"] = user_message
            if response is not None:
                entry["response"] = response
        _log(entry)

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    last_error: str | None = None

    # The agent system prompts are large and identical across every target and
    # every run, so mark the system block for prompt caching: the API caches it
    # on the first call and reads it back cheaply on subsequent ones (5-min TTL).
    # Wrapper-only — the prompt TEXT is untouched; this just sends it as a single
    # cache-controlled content block instead of a bare string.
    system_blocks = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]

    for attempt in (1, 2):
        start = time.perf_counter()
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_blocks,
                tools=[response_schema],
                tool_choice={"type": "tool", "name": tool_name},
                messages=messages,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            err = f"{type(e).__name__}: {e}"
            _emit({
                "model": model,
                "system_prompt_hash": sys_hash,
                "user_message_first_100_chars": msg_preview,
                "response_chars": 0,
                "latency_ms": latency_ms,
                "status": "error",
                "error": err,
                "attempt": attempt,
            })
            raise LLMCallError(err) from e

        latency_ms = int((time.perf_counter() - start) * 1000)
        tool_use = next(
            (b for b in response.content if b.type == "tool_use" and b.name == tool_name),
            None,
        )

        if tool_use is not None:
            result = dict(tool_use.input) if not isinstance(tool_use.input, dict) else tool_use.input
            _emit({
                "model": model,
                "system_prompt_hash": sys_hash,
                "user_message_first_100_chars": msg_preview,
                "response_chars": len(json.dumps(result, ensure_ascii=False)),
                "latency_ms": latency_ms,
                "status": "success",
                "attempt": attempt,
                **_usage_dict(response),
            }, response=result)
            return result

        last_error = f"Model did not call tool {tool_name!r}"
        _emit({
            "model": model,
            "system_prompt_hash": sys_hash,
            "user_message_first_100_chars": msg_preview,
            "response_chars": 0,
            "latency_ms": latency_ms,
            "status": "retry" if attempt == 1 else "error",
            "error": last_error,
            "attempt": attempt,
            **_usage_dict(response),
        })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": (
                f"You must call the {tool_name} tool with valid input that matches its "
                "schema. Do not respond with text. Call the tool now."
            ),
        })

    raise LLMCallError(last_error or "Unknown LLM call failure")
