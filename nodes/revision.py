"""Optional self-revision pass over the generated answer."""

import httpx
import logging
import re

import deepseek_client
import langfuse_client
from deepseek_optimizer import DeepSeekOptimizer


def needs_revision(state: dict) -> bool:
    """
    Determina se a resposta precisa de revisão.
    Pula revisão para respostas já otimizadas.
    """
    response = state.get("response", "")

    # Tool-driven replies (lead confirmation, booking link) are already curated — a
    # 500-char rewrite could mangle them or drop the booking URL, so never revise them.
    if state.get("tool_results"):
        return False

    # Critérios para PULAR revisão:
    # 1. Resposta curta e direta (menos de 1000 caracteres)
    # 2. Não contém informações sensíveis (emails, telefones)
    # 3. Foi gerada via fast track ou cache
    # 4. Já está bem formatada

    skip_revision = (
        len(response) < 1000 and
        "@" not in response and
        not re.search(r'\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,4}', response) and  # No phone numbers
        not re.search(r'whatsapp|wpp|zap|telefone|celular|ligar', response.lower()) and
        (state.get("fast_track", False) or state.get("cached", False))
    )

    return not skip_revision


async def revise_response(state: dict) -> dict:
    # Verificar se precisa de revisão
    if not needs_revision(state):
        logging.info("Skipping revision - response already optimized")
        return {
            **state,
            "revised_response": state["response"],
            "step": "revision_skipped"
        }

    trace = state.get("langfuse_trace")

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
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.5},
            prompt=revise_prompt if revise_prompt else None,
        )

        response = await deepseek_client.chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.5,
            extra_headers=optimization_headers,
        )
    except httpx.ReadTimeout:
        logging.error("Request timed out in DeepSeek API call for response revision")
        return {
            **state,
            "revised_response": "Sorry, the service is taking too long to revise the response. Please try again later.",
            "step": "error_timeout"
        }

    data = response.json()

    # Rastrear uso de tokens
    usage = data.get("usage", {})
    if usage:
        DeepSeekOptimizer.update_usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cache_hit=response.headers.get("X-Cache-Status") == "hit"
        )

    # Guard against API errors (401/429/5xx return JSON without "choices" -> KeyError).
    # Revision is optional polish, so fall back to the already-generated answer.
    try:
        revised = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        logging.error("revise_response: unexpected DeepSeek response: %s", str(data)[:200])
        fallback = state.get("response") or state.get("revised_response") or ""
        return {**state, "revised_response": fallback, "step": "revise_response_skipped"}

    # End generation AFTER LLM call
    langfuse_client.end_llm_generation(
        generation=generation,
        output_content=revised,
        usage=usage,
    )

    revised = revised.replace('\n\n', '\n').replace('\n', '\n\n')
    return {**state, "revised_response": revised, "step": "revise_response"}
