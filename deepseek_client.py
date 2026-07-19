"""
Single entry point for DeepSeek's OpenAI-compatible chat API.

The same httpx POST was copy-pasted at five call sites (intent detection, the tool loop,
revision, off-topic, and the eval judge), each repeating the URL, auth headers, model name,
timeout, and error-prone response unpack. A change to any of those had to be made in five
places. This centralizes the call so provider/model/timeout live in one spot (config).
"""

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
) -> httpx.Response:
    """
    POST a chat completion to DeepSeek and return the raw httpx response. Callers do their own
    `.json()` / `data["choices"]` extraction / usage tracking, so this stays a thin transport
    seam (URL, auth, model, timeout in one place), not a leaky abstraction over the varied
    response handling — and callers that need to see a non-JSON/error body still can.
    """
    body: dict = {"model": DEEPSEEK_MODEL, "messages": messages, "temperature": temperature}
    if tools is not None:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if response_format is not None:
        body["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(DEEPSEEK_API_URL, headers=headers, json=body)
