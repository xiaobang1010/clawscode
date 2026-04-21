from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import AsyncGenerator

from openai import APIStatusError, AsyncOpenAI, RateLimitError


@dataclass
class StreamEvent:
    type: str
    data: dict


def create_client(api_key: str, base_url: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


async def create_stream(
    messages: list[dict],
    tools: list[dict],
    system: str,
    model: str = "ZhipuAI/GLM-5",
    api_key: str | None = None,
    base_url: str = "https://api-inference.modelscope.cn/v1",
    cache_system_prompt: bool = True,
    cache_messages: bool = False,
) -> AsyncGenerator[StreamEvent, None]:
    client = create_client(api_key or "", base_url)

    system_msg: dict = {"role": "system", "content": system}
    if cache_system_prompt:
        system_msg["cache_control"] = {"type": "ephemeral"}
    openai_messages = [system_msg] + messages

    kwargs: dict = {
        "model": model,
        "messages": openai_messages,
        "max_tokens": 16384,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        kwargs["tools"] = tools

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.chat.completions.create(**kwargs)
            break
        except RateLimitError as exc:
            last_exc = exc
        except APIStatusError as exc:
            if exc.status_code in (429, 500, 503):
                last_exc = exc
            else:
                raise
        else:
            continue
        await asyncio.sleep(2**attempt)
    else:
        raise last_exc

    start_time = time.monotonic()
    has_text_delta = False
    has_usage = False
    _EXCLUDED_DELTA_ATTRS = frozenset({
        "role", "content", "reasoning_content",
        "tool_calls", "function_call",
    })

    async for chunk in response:
        if not chunk.choices:
            if hasattr(chunk, "usage") and chunk.usage:
                u = chunk.usage
                if getattr(u, "prompt_tokens", 0) > 0 or getattr(u, "completion_tokens", 0) > 0:
                    has_usage = True
                    yield StreamEvent(type="usage", data={
                        "input_tokens": getattr(u, "prompt_tokens", 0),
                        "output_tokens": getattr(u, "completion_tokens", 0),
                        "duration_ms": (time.monotonic() - start_time) * 1000,
                        "model": model,
                    })
            continue

        delta = chunk.choices[0].delta

        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            has_text_delta = True
            yield StreamEvent(type="reasoning_delta", data={"text": delta.reasoning_content})

        if delta.content:
            has_text_delta = True
            yield StreamEvent(type="text_delta", data={"text": delta.content})

        if not (hasattr(delta, "reasoning_content") and delta.reasoning_content) and not delta.content:
            for attr_name in vars(delta):
                if attr_name.startswith("_") or attr_name in _EXCLUDED_DELTA_ATTRS:
                    continue
                value = getattr(delta, attr_name, None)
                if isinstance(value, str) and value:
                    has_text_delta = True
                    yield StreamEvent(type="text_delta", data={"text": value})
                    break

        if delta.tool_calls:
            for tc in delta.tool_calls:
                yield StreamEvent(
                    type="tool_calls",
                    data={
                        "id": tc.id,
                        "index": tc.index,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                )

        finish_reason = chunk.choices[0].finish_reason
        if finish_reason == "stop":
            yield StreamEvent(type="message_stop", data={})
        elif finish_reason == "tool_calls":
            yield StreamEvent(type="tool_calls_done", data={})
        if finish_reason is not None:
            yield StreamEvent(type="finish_reason", data={"reason": finish_reason})

    if has_usage and not has_text_delta:
        yield StreamEvent(type="debug", data={
            "message": "stream contained usage but no text_delta or reasoning_delta was emitted",
            "model": model,
        })
