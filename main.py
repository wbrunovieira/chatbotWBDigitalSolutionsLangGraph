from fastapi import FastAPI, Request
from langgraph.graph import StateGraph, END, START
from typing import TypedDict, List, Dict, Any
from qdrant_client import QdrantClient
import httpx
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
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
    async with httpx.AsyncClient() as client:
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
    data = response.json()
    intent = data["choices"][0]["message"]["content"].strip()
    return {**state, "intent": intent, "step": "detectar_intencao"}

# -------------------------------
# Nó: Gera resposta com DeepSeek
# -------------------------------
async def gerar_resposta(state: GraphState) -> GraphState:
    messages = state.get("messages", []) + [{"role": "user", "content": state["input"]}]
    
    async with httpx.AsyncClient() as client:
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

    async with httpx.AsyncClient() as client:
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
    data = response.json()
    revised = data["choices"][0]["message"]["content"]
    return {**state, "revised_response": revised, "step": "revisar_resposta"}

# -------------------------------
# Criação do Grafo
# -------------------------------
workflow = StateGraph(GraphState)

workflow.add_node("intencao", detectar_intencao)
workflow.add_node("responder", gerar_resposta)
workflow.add_node("revisor", revisar_resposta)

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

# Fim após revisão
workflow.add_edge("revisor", END)

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

    # Instancia cliente Qdrant Cloud
    qdrant = QdrantClient(
        url=os.getenv("QDRANT_HOST"),
        api_key=os.getenv("QDRANT_API_KEY"),
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