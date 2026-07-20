"""
Single entry point for DeepSeek's OpenAI-compatible chat API.

The same httpx POST was copy-pasted at five call sites (intent detection, the tool loop,
revision, off-topic, and the eval judge), each repeating the URL, auth headers, model name,
timeout, and error-prone response unpack. A change to any of those had to be made in five
places. This centralizes the call so provider/model/timeout live in one spot (config).
"""

import json

import httpx

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL

DEFAULT_TIMEOUT = 30.0


async def chat_completion(
    messages: list,
    *,
    temperature: float = 0.7,
    tools: list | None = None,
    response_format: dict | None = None,
    extra_headers: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    model: str | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
) -> httpx.Response:
    """
    POST a chat completion to an OpenAI-compatible endpoint and return the raw httpx response.
    Defaults to DeepSeek (config), but model/api_url/api_key can be overridden so the same
    transport serves per-task model routing and a secondary provider (see llm.py). Callers do
    their own `.json()` / `data["choices"]` extraction / usage tracking, so this stays a thin
    transport seam, not a leaky abstraction over the varied response handling.
    """
    body: dict = {
        "model": model or DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if tools is not None:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if response_format is not None:
        body["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {api_key or DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(api_url or DEEPSEEK_API_URL, headers=headers, json=body)


async def stream_chat_completion(
    messages: list,
    *,
    temperature: float = 0.7,
    extra_headers: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    model: str | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
):
    """Stream an OpenAI-compatible chat completion, yielding content-delta strings (#14).

    Async generator over the SSE `data:` lines: parses each chunk's
    choices[0].delta.content and yields non-empty deltas, stopping at `[DONE]`. Malformed
    chunks are skipped rather than raising, so one bad line can't abort a live stream.
    """
    body = {
        "model": model or DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key or DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", api_url or DEEPSEEK_API_URL, headers=headers, json=body) as resp:
            resp.raise_for_status()  # a 4xx/5xx surfaces to the endpoint, which degrades gracefully
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (ValueError, KeyError, IndexError, TypeError):
                    continue
                if delta:
                    yield delta
