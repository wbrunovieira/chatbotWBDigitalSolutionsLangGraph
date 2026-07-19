"""
Process-wide Qdrant client singleton.

The client used to be created fresh on every /chat request and injected into the graph
state. That is wasteful (a new connection per request) and, more importantly, a live client
is not serializable — which breaks the LangGraph checkpointer (it serializes the state to
persist conversation memory). Nodes now fetch the shared client from here instead of reading
it out of the state.
"""

from qdrant_client import QdrantClient

from config import QDRANT_API_KEY, QDRANT_HOST

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_HOST, api_key=QDRANT_API_KEY)
    return _client


def set_qdrant_client(client) -> None:
    """Override the singleton. Test seam — production code never calls this."""
    global _client
    _client = client
