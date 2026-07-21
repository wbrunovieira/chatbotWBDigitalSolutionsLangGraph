"""Optional self-revision pass over the generated answer."""

import httpx
import logging

import config
from providers import deepseek_client  # noqa: F401  (tests patch nodes.deepseek_client; llm delegates to it)
from observability import langfuse_client
from providers import llm
from providers.deepseek_optimizer import DeepSeekOptimizer


def needs_revision(state: dict) -> bool:
    """Whether to spend a second LLM call polishing the answer.

    Revision is a second DeepSeek round-trip, so it stays off the hot path: it only helps
    long answers that need trimming toward the ~500-char target, so we gate on length.
    Short, direct replies are already fine and are returned as generated. Tool-driven
    replies (booking link, lead confirmation) are curated and must never be rewritten —
    a rewrite could mangle them or drop the booking URL.
    """
    if state.get("tool_results"):
        return False

    response = state.get("response", "") or ""
    return len(response) > config.REVISION_MAX_LENGTH


def _keep_original(state: dict) -> dict:
    """Revision failed/timed out — fall back to the already-generated answer."""
    original = state.get("response") or state.get("revised_response") or ""
    return {**state, "revised_response": original, "step": "revise_response_skipped"}


async def revise_response(state: dict) -> dict:
    # Verificar se precisa de revisão
    if not needs_revision(state):
        logging.info("Skipping revision - response already optimized")
        return {
            **state,
            "revised_response": state["response"],
            "step": "revision_skipped"
        }

    trace = langfuse_client.get_current_trace()

    # Get revision prompt from Langfuse
    revise_prompt = langfuse_client.get_prompt("revise_response")
    if revise_prompt:
        prompt = revise_prompt.compile(response=state["response"])
    else:
        prompt = (
            "Rewrite the following response to make it clearer and friendlier, keeping a professional tone.\n"
            "Maximum 500 characters. Preserve the original language.\n"
            "Reply ONLY with the improved text.\n\n"
            f"Original response: {state['response']}"
        )
    try:
        # Adicionar headers de otimização
        optimization_headers = DeepSeekOptimizer.get_optimization_headers()

        # Start generation BEFORE LLM call
        generation = langfuse_client.start_llm_generation(
            trace=trace,
            name="revise_response",
            model="deepseek-v4-flash",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.5},
            prompt=revise_prompt if revise_prompt else None,
        )

        response = await llm.chat_completion(
            [{"role": "user", "content": prompt}],
            task="revision",
            temperature=0.5,
            extra_headers=optimization_headers,
        )
    except httpx.HTTPError as exc:
        # Revision is optional polish — on ANY transport error (timeout, connect, protocol),
        # keep the already-generated answer. Must NOT be ReadTimeout-only: a ConnectError here
        # would otherwise 500 the request and throw away a good reply that was ready to send.
        logging.error("revise_response: DeepSeek call failed (%s); keeping the original answer", exc)
        return _keep_original(state)

    # Parse + extract, all guarded. ANY failure — a non-JSON gateway body (502 HTML ->
    # JSONDecodeError, which used to 500), or JSON without "choices" — falls back to the
    # generated answer, since revision is optional.
    try:
        data = response.json()
        usage = data.get("usage", {})
        if usage:
            DeepSeekOptimizer.update_usage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                cache_hit=response.headers.get("X-Cache-Status") == "hit",
            )
        revised = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        logging.error("revise_response: unexpected DeepSeek response: %s", response.text[:200])
        return _keep_original(state)

    # End generation AFTER LLM call
    langfuse_client.end_llm_generation(
        generation=generation,
        output_content=revised,
        usage=usage,
    )

    revised = revised.replace('\n\n', '\n').replace('\n', '\n\n')
    return {**state, "revised_response": revised, "step": "revise_response"}
