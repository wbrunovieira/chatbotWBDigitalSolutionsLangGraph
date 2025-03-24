from fastapi import FastAPI, Request
from langgraph.graph import StateGraph, END, START
from typing import TypedDict, List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
import httpx
import os
import re
from dotenv import load_dotenv
import logging
import time

# Configuração do logging
logging.basicConfig(level=logging.INFO)

load_dotenv()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# -------------------------------
# Define o estado do grafo
# -------------------------------
class GraphState(TypedDict, total=False):
    input: str
    response: str
    revised_response: str
    messages: List[Dict[str, str]]
    intent: str
    memory: Dict[str, Any]
    user_id: str
    metadata: Dict[str, Any]
    step: str
    qdrant_client: QdrantClient

# -------------------------------
# Nó: Detecta intenção
# -------------------------------


async def detectar_intencao(state: GraphState) -> GraphState:
    prompt = f"""
    Classifique a intenção desta mensagem em uma palavra-chave:
    "{state['input']}"
    Intenções possíveis: perguntar_servicos, pedir_orcamento, conversar_com_atendente, agendar_reuniao
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5
                }
            )
    except httpx.ReadTimeout:
        logging.error("Tempo limite excedido na chamada da DeepSeek API")
        return {**state, "response": "Desculpe, o serviço está demorando para responder. Tente novamente em alguns instantes.", "step": "erro_timeout"}
    
    data = response.json()
    raw_intent = data["choices"][0]["message"]["content"].strip()
    
    # Tenta extrair a intenção entre aspas, se possível
    match = re.search(r'"([^"]+)"', raw_intent)
    intent = match.group(1) if match else raw_intent

    # Define as intenções esperadas e, se não bater, usa um padrão
    expected_intents = {"pedir_orcamento", "perguntar_servicos", "conversar_com_atendente", "agendar_reuniao"}
    if intent not in expected_intents:
        logging.error("Intenção não reconhecida: %s. Usando 'perguntar_servicos' como padrão.", intent)
        intent = "perguntar_servicos"
    
    return {**state, "intent": intent, "step": "detectar_intencao"}
# -------------------------------
# Nó: Gera resposta com DeepSeek
# -------------------------------

async def gerar_resposta(state: GraphState) -> GraphState:
    messages = state.get("messages", []) + [{"role": "user", "content": state["input"]}]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": 0.7
                }
            )
    except httpx.ReadTimeout:
        logging.error("Tempo limite excedido na chamada da DeepSeek API para gerar resposta")
        return {
            **state,
            "response": "Desculpe, o serviço está demorando para responder. Tente novamente em alguns instantes.",
            "step": "erro_timeout"
        }
    
    data = response.json()
    reply = data["choices"][0]["message"]["content"]
    
    return {
        **state,
        "response": reply,
        "messages": messages + [{"role": "assistant", "content": reply}],
        "step": "gerar_resposta"
    }

# -------------------------------
# Nó: Revisa resposta
# -------------------------------
async def revisar_resposta(state: GraphState) -> GraphState:
    prompt = f"Reescreva a seguinte resposta para ficar mais clara e amigável:\n\n{state['response']}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5
                }
            )
    except httpx.ReadTimeout:
        logging.error("Tempo limite excedido na chamada da DeepSeek API para revisar resposta")
        return {
            **state,
            "revised_response": "Desculpe, o serviço está demorando para revisar a resposta. Tente novamente em alguns instantes.",
            "step": "erro_timeout"
        }
    
    data = response.json()
    revised = data["choices"][0]["message"]["content"]
    return {**state, "revised_response": revised, "step": "revisar_resposta"}

# -------------------------------
# Nó: Salvar log no Qdrant
# -------------------------------
async def salvar_log_qdrant(state: GraphState) -> GraphState:
    # Extrai os dados que serão salvos
    data_to_save = {
        "user_id": state.get("user_id"),
        "input": state.get("input"),
        "response": state.get("response"),
        "revised_response": state.get("revised_response"),
        "intent": state.get("intent"),
        "messages": state.get("messages")
    }
    # Loga os dados antes de salvar
    logging.info("Salvando no Qdrant: %s", data_to_save)
    print("Dados enviados para o Qdrant:", data_to_save)
    
    # Exemplo de ponto para salvar (certifique-se de que a coleção 'chat_logs' exista)
    point = {
        "id": int(time.time()),
        "vector": [0.0] * 128,  # vetor dummy; ajuste conforme necessário
        "payload": data_to_save,
    }
    try:
        state["qdrant_client"].upsert(
            collection_name="chat_logs",
            points=[point]
        )
        logging.info("Log salvo no Qdrant com sucesso.")
    except Exception as e:
        logging.error("Erro ao salvar log no Qdrant: %s", e)
    
    return state

# -------------------------------
# Criação do Grafo
# -------------------------------
workflow = StateGraph(GraphState)

workflow.add_node("intencao", detectar_intencao)
workflow.add_node("responder", gerar_resposta)
workflow.add_node("revisor", revisar_resposta)
workflow.add_node("salvar_log_qdrant", salvar_log_qdrant)

workflow.set_entry_point("intencao")

# Roteia com base na intenção
workflow.add_conditional_edges(
    "intencao",
    lambda state: state.get("intent", ""),
    {
        "pedir_orcamento": "responder",
        "perguntar_servicos": "responder",
        "conversar_com_atendente": END,
        "agendar_reuniao": "responder"
    }
)

# Após responder, sempre revisar
workflow.add_edge("responder", "revisor")
# Após revisar, salvar log no Qdrant
workflow.add_edge("revisor", "salvar_log_qdrant")
# Fim após salvar log
workflow.add_edge("salvar_log_qdrant", END)

graph = workflow.compile()

# -------------------------------
# FastAPI
# -------------------------------
app = FastAPI()
@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    user_input = body.get("message")
    user_id = body.get("user_id", "anon")

    # Instancia o cliente Qdrant Cloud
    qdrant = QdrantClient(
        url=os.getenv("QDRANT_HOST"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )

    # Verifica e cria a coleção 'chat_logs' se não existir.
    try:
        qdrant.get_collection(collection_name="chat_logs")
    except Exception as e:
        logging.info("Coleção 'chat_logs' não encontrada. Criando a coleção...")
        from qdrant_client.http.models import VectorParams, Distance
        qdrant.create_collection(
            collection_name="chat_logs",
            vectors_config=VectorParams(size=128, distance=Distance.COSINE)
        )

    state = {
        "input": user_input,
        "user_id": user_id,
        "messages": [],
        "memory": {},
        "metadata": {},
        "qdrant_client": qdrant
    }

    result = await graph.ainvoke(state)

    return {
        "resposta_bruta": result.get("response"),
        "resposta_revisada": result.get("revised_response"),
        "intent_detectada": result.get("intent"),
        "etapa_final": result.get("step")
    }
