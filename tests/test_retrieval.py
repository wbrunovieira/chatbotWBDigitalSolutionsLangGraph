"""Top-k company-context retrieval over chunks, with score threshold + trace citations."""

import pytest

import db
import nodes


@pytest.fixture(autouse=True)
def reset_qdrant_singleton():
    # Nodes fetch the Qdrant client from the db singleton, not from state; reset between tests.
    yield
    db.set_qdrant_client(None)


class FakePoint:
    def __init__(self, payload, score):
        self.payload = payload
        self.score = score


class FakeQdrant:
    def __init__(self, results=None, raise_on_search=False):
        self._results = results or []
        self._raise = raise_on_search
        self.last_kwargs = None

    def search(self, **kwargs):
        self.last_kwargs = kwargs
        if self._raise:
            raise RuntimeError("qdrant down")
        return self._results


@pytest.fixture(autouse=True)
def stub_embedding(monkeypatch):
    # Retrieval embeds the query; don't download/run the ONNX model in tests.
    monkeypatch.setattr(nodes, "compute_embedding", lambda text: [0.1] * 384)


class TestRetrieveCompanyContext:
    async def test_joins_topk_chunks_and_records_citations(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(nodes, "update_trace", lambda trace, metadata=None: captured.update(metadata or {}))
        client = FakeQdrant(results=[
            FakePoint({"text": "Websites chunk", "section": "Services > Websites"}, 0.82),
            FakePoint({"text": "Automation chunk", "section": "Services > Automation"}, 0.55),
        ])
        db.set_qdrant_client(client)
        state = {"user_input": "vocês fazem sites?", "langfuse_trace": object()}

        out = await nodes.retrieve_company_context(state)

        assert "Websites chunk" in out["company_context"]
        assert "Automation chunk" in out["company_context"]
        assert client.last_kwargs["limit"] == nodes.COMPANY_TOP_K
        assert client.last_kwargs["score_threshold"] == nodes.COMPANY_SCORE_THRESHOLD
        # citations attached to the trace
        assert captured["rag_sources"][0]["section"] == "Services > Websites"
        assert captured["rag_sources"][0]["score"] == pytest.approx(0.82)

    async def test_legacy_single_doc_payload_still_works(self):
        # Before the first chunked ingest, points carry the old "company_info" key.
        client = FakeQdrant(results=[FakePoint({"company_info": "Legacy whole doc"}, 0.9)])
        db.set_qdrant_client(client)
        state = {"user_input": "oi", "langfuse_trace": None}
        out = await nodes.retrieve_company_context(state)
        assert out["company_context"] == "Legacy whole doc"

    async def test_no_hits_yields_empty_context_and_no_sources(self):
        client = FakeQdrant(results=[])
        db.set_qdrant_client(client)
        state = {"user_input": "capital da França", "langfuse_trace": None}
        out = await nodes.retrieve_company_context(state)
        assert out["company_context"] == ""
        assert out["rag_sources"] == []

    async def test_search_error_degrades_gracefully(self):
        client = FakeQdrant(raise_on_search=True)
        db.set_qdrant_client(client)
        state = {"user_input": "oi", "langfuse_trace": None}
        out = await nodes.retrieve_company_context(state)
        assert out["company_context"] == ""
        assert out["step"] == "retrieve_company_context"


class FlakyLogClient:
    """First chat_logs upsert fails (collection missing); after ensure it succeeds."""

    def __init__(self):
        self.upserts = 0
        self.created = False

    def upsert(self, collection_name, points):
        self.upserts += 1
        if self.upserts == 1:
            raise RuntimeError("collection 'chat_logs' not found")

    def get_collection(self, collection_name):
        raise RuntimeError("missing")

    def create_collection(self, collection_name, vectors_config):
        self.created = True


class TestSaveLogRetry:
    async def test_creates_chat_logs_and_retries_when_missing(self):
        # If startup skipped collection creation (Qdrant was down at boot), the write path
        # must self-heal: create chat_logs and retry, not silently drop conversation memory.
        client = FlakyLogClient()
        db.set_qdrant_client(client)
        state = {
            "user_id": "u1", "user_input": "oi", "response": "olá",
            "revised_response": "olá!", "intent": "greeting", "language": "pt-BR",
            "current_page": "/", "tool_results": [],
        }
        await nodes.save_log_qdrant(state)
        assert client.created is True     # collection ensured
        assert client.upserts == 2        # failed once, retried after create
