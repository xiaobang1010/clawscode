from __future__ import annotations

import asyncio
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
) -> AsyncGenerator[StreamEvent, None]:
    client = create_client(api_key or "", base_url)

    openai_messages = [{"role": "system", "content": system}] + messages

    kwargs: dict = {
        "model": model,
        "messages": openai_messages,
        "max_tokens": 16384,
        "stream": True,
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

    async for chunk in response:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            yield StreamEvent(type="reasoning_delta", data={"text": delta.reasoning_content})

        if delta.content:
            yield StreamEvent(type="text_delta", data={"text": delta.content})

        if delta.tool_calls:
            for tc in delta.tool_calls:
                yield StreamEvent(
                    type="tool_calls",
                    data={
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                )

        if chunk.choices[0].finish_reason == "stop":
            yield StreamEvent(type="message_stop", data={})
