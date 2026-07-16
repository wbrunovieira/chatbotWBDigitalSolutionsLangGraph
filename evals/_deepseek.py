"""
Resilient DeepSeek call for the eval runners.

An eval GATE must distinguish a real quality regression from a transient infra blip — a
429/5xx/timeout that reds the build looks exactly like a regression otherwise. So this
retries with backoff and, if the API is genuinely unreachable, raises InfraError (which the
runners turn into a distinct, legible failure) rather than crashing mid-parse.
"""

import os
import time

import httpx


class InfraError(Exception):
    """DeepSeek was unreachable — an infra problem, NOT a quality regression."""


def chat(body: dict, *, retries: int = 3) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = httpx.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s backoff
    raise InfraError(f"DeepSeek unreachable after {retries} attempts: {last}")
