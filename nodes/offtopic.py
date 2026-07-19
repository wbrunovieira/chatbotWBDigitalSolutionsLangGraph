"""Off-topic redirect response."""

import logging

import deepseek_client
import langfuse_client


async def generate_off_topic_response(state: dict) -> dict:
    """
    Gera resposta para perguntas fora do escopo usando prompt do Langfuse.
    """
    user_input = state.get("user_input", "")
    language = state.get("language", "pt-BR")
    trace = state.get("langfuse_trace")

    # Buscar prompt do Langfuse
    off_topic_prompt = langfuse_client.get_prompt("generate_off_topic")

    if off_topic_prompt:
        try:
            prompt = off_topic_prompt.compile(
                user_input=user_input,
                language=language,
            )
        except Exception as e:
            logging.warning(f"Error compiling off_topic prompt: {e}")
            prompt = f"User asked '{user_input}' which is off-topic. Politely redirect to digital services in {language}."
    else:
        prompt = f"User asked '{user_input}' which is off-topic. Politely redirect to digital services in {language}."

    try:
        # Start generation BEFORE LLM call
        generation = langfuse_client.start_llm_generation(
            trace=trace,
            name="generate_off_topic",
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.7},
            prompt=off_topic_prompt,
        )

        resp = await deepseek_client.chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        data = resp.json()
        response = data["choices"][0]["message"]["content"].strip()

        # End generation AFTER LLM call
        langfuse_client.end_llm_generation(
            generation=generation,
            output_content=response,
            usage=data.get("usage"),
        )
    except Exception as e:
        logging.error(f"Error generating off-topic response: {e}")
        response = "Desculpe, sou especializado em soluções digitais. Posso ajudar com sites, automação ou IA?"

    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_off_topic_response",
        "intent": "off_topic"
    }
