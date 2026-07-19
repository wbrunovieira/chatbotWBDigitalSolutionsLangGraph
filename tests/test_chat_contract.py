"""
The /chat contract with the site widget, and the abuse controls wired around it.

The widget posts {message, user_id, language, current_page, page_url, timestamp} and
reads back a fixed response shape. Hardening must not move either.
"""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import db
import main
import security
from deepseek_optimizer import add_request_cost

ALLOWED_ORIGIN = "https://www.wbdigitalsolutions.com"

# Exactly what the site sends today.
VALID_PAYLOAD = {
    "message": "Quanto custa um site?",
    "user_id": "user-123",
    "language": "pt-BR",
    "current_page": "/websites",
    "page_url": "https://www.wbdigitalsolutions.com/websites",
    "timestamp": "2026-07-14T10:00:00Z",
}

# Exactly what the widget reads back.
EXPECTED_RESPONSE_KEYS = {
    "raw_response",
    "revised_response",
    "response_parts",
    "detected_intent",
    "final_step",
    "language_used",
    "context_page",
    "is_greeting",
    "cached",
}

# Cost the stubbed graph bills per run.
STUB_COST_USD = 0.02


class FakeQdrant:
    """Collections already exist and are populated, so /chat's bootstrap is a no-op."""

    def get_collection(self, collection_name):
        return SimpleNamespace(points_count=1)

    def create_collection(self, **kwargs):
        raise AssertionError("tests must not create collections")

    def upsert(self, **kwargs):
        pass

    def search(self, **kwargs):
        return []


@pytest.fixture
def graph_calls(monkeypatch):
    """Stub the LangGraph run and record invocations, so tests can assert it was skipped."""
    calls = []

    async def fake_ainvoke(state, config=None):
        calls.append(state)
        add_request_cost(STUB_COST_USD)  # stand in for the real DeepSeek calls
        return {
            **state,
            "response": "Depende do escopo.",
            "revised_response": "Depende do escopo. Fale com a gente!",
            "intent": "request_quote",
            "step": "revise_response",
        }

    monkeypatch.setattr(main.graph, "ainvoke", fake_ainvoke)
    return calls


@pytest_asyncio.fixture
async def client(monkeypatch, redis_fake, limits, graph_calls):
    """Async client with every external dependency stubbed: no network, no spend."""
    db.set_qdrant_client(FakeQdrant())  # nodes read the client from the db singleton
    monkeypatch.setattr(main, "create_trace", lambda **kwargs: None)
    monkeypatch.setattr(main, "update_trace", lambda *args, **kwargs: None)

    async def no_eval(**kwargs):
        return None

    monkeypatch.setattr(main, "evaluate_response", no_eval)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    db.set_qdrant_client(None)


async def post(client, payload=None, ip="203.0.113.10", origin=ALLOWED_ORIGIN):
    return await client.post(
        "/chat",
        json=VALID_PAYLOAD if payload is None else payload,
        headers={"X-Real-IP": ip, "Origin": origin},
    )


class TestFrontendContract:
    async def test_accepts_the_exact_payload_the_site_sends(self, client):
        assert (await post(client)).status_code == 200

    async def test_response_shape_is_unchanged(self, client):
        body = (await post(client)).json()
        assert set(body.keys()) == EXPECTED_RESPONSE_KEYS

    async def test_all_fields_reach_the_graph(self, client, graph_calls):
        await post(client)
        state = graph_calls[0]

        assert state["user_input"] == VALID_PAYLOAD["message"]
        assert state["user_id"] == VALID_PAYLOAD["user_id"]
        assert state["language"] == VALID_PAYLOAD["language"]
        assert state["current_page"] == VALID_PAYLOAD["current_page"]
        assert state["metadata"]["page_url"] == VALID_PAYLOAD["page_url"]
        assert state["metadata"]["timestamp"] == VALID_PAYLOAD["timestamp"]

    async def test_optional_fields_keep_their_old_defaults(self, client, graph_calls):
        await post(client, {"message": "oi"})
        state = graph_calls[0]

        assert state["user_id"] == "anon"
        assert state["language"] == "pt-BR"
        assert state["current_page"] == "/"

    async def test_numeric_timestamp_is_accepted(self, client):
        # Some widget builds send Date.now() instead of an ISO string; a strict `str`
        # field would 422 those and break the chat.
        response = await post(client, {**VALID_PAYLOAD, "timestamp": 1752489600000})
        assert response.status_code == 200

    async def test_unknown_fields_are_ignored_not_rejected(self, client):
        # The site must be able to add a field without taking the backend down.
        response = await post(client, {**VALID_PAYLOAD, "session_id": "abc"})
        assert response.status_code == 200


class TestInputValidation:
    async def test_message_is_required(self, client, graph_calls):
        assert (await post(client, {"user_id": "x"})).status_code == 422
        assert graph_calls == []

    async def test_empty_message_is_rejected(self, client):
        assert (await post(client, {**VALID_PAYLOAD, "message": "   "})).status_code == 422

    async def test_oversized_message_never_reaches_the_llm(self, client, graph_calls, limits):
        # The token-amplification bomb: nginx accepted a 10MB body, and one /chat
        # request fans out into up to 3 DeepSeek calls.
        huge = "a" * (limits["MAX_MESSAGE_LENGTH"] + 1)

        assert (await post(client, {**VALID_PAYLOAD, "message": huge})).status_code == 422
        assert graph_calls == []

    async def test_message_at_the_limit_is_accepted(self, client, limits):
        at_limit = "a" * limits["MAX_MESSAGE_LENGTH"]
        assert (await post(client, {**VALID_PAYLOAD, "message": at_limit})).status_code == 200


class TestRateLimiting:
    async def test_returns_429_past_the_limit(self, client, limits):
        for i in range(limits["RATE_LIMIT_PER_MINUTE"]):
            response = await post(client, {**VALID_PAYLOAD, "message": f"msg {i}"})
            assert response.status_code == 200

        blocked = await post(client, {**VALID_PAYLOAD, "message": "one too many"})
        assert blocked.status_code == 429
        assert blocked.headers["retry-after"] == "60"

    async def test_429_still_carries_cors_headers(self, client, limits):
        """
        Regression guard for why these are dependencies, not middleware: middleware
        added after CORSMiddleware sits *outside* it, so its 429 would ship without
        CORS headers and the widget would report a bogus "CORS error" instead of
        showing the rate-limit message.
        """
        for i in range(limits["RATE_LIMIT_PER_MINUTE"]):
            await post(client, {**VALID_PAYLOAD, "message": f"msg {i}"})

        blocked = await post(client, {**VALID_PAYLOAD, "message": "one too many"})
        assert blocked.status_code == 429
        assert blocked.headers["access-control-allow-origin"] == ALLOWED_ORIGIN

    async def test_limits_are_tracked_per_ip(self, client, limits):
        for i in range(limits["RATE_LIMIT_PER_MINUTE"]):
            await post(client, {**VALID_PAYLOAD, "message": f"msg {i}"}, ip="203.0.113.10")

        assert (await post(client, ip="203.0.113.10")).status_code == 429
        assert (await post(client, ip="198.51.100.20")).status_code == 200


class TestSpendCap:
    async def test_returns_503_and_skips_the_llm_when_the_budget_is_gone(
        self, client, limits, graph_calls
    ):
        await security.record_spend("9.9.9.9", limits["DAILY_SPEND_LIMIT_USD"])
        graph_calls.clear()

        blocked = await post(client, ip="198.51.100.77")

        assert blocked.status_code == 503
        assert graph_calls == [], "the spend cap must trip before the LLM is called"

    async def test_503_carries_cors_headers(self, client, limits):
        await security.record_spend("9.9.9.9", limits["DAILY_SPEND_LIMIT_USD"])

        blocked = await post(client, ip="198.51.100.77")
        assert blocked.status_code == 503
        assert blocked.headers["access-control-allow-origin"] == ALLOWED_ORIGIN

    async def test_a_successful_request_bills_its_cost(self, client):
        await post(client, ip="203.0.113.42")

        snapshot = await security.get_spend_snapshot()
        assert snapshot["spent_usd"] == pytest.approx(STUB_COST_USD)

    async def test_cached_responses_cost_nothing_and_skip_the_graph(self, client, graph_calls):
        first = await post(client)
        assert first.status_code == 200
        assert len(graph_calls) == 1

        second = await post(client)
        assert second.status_code == 200
        assert second.json()["cached"] is True
        assert len(graph_calls) == 1, "a Redis cache hit must not re-run the graph"

        # A cache hit skips DeepSeek entirely, so it must not consume budget either.
        snapshot = await security.get_spend_snapshot()
        assert snapshot["spent_usd"] == pytest.approx(STUB_COST_USD)

    async def test_cache_is_isolated_per_user(self, client, graph_calls):
        # Now that responses are conversation-dependent, one visitor's cached answer must
        # never be served to another — the cache key includes user_id.
        await post(client, {**VALID_PAYLOAD, "user_id": "user-A"})
        assert len(graph_calls) == 1

        other = await post(client, {**VALID_PAYLOAD, "user_id": "user-B"})
        assert other.json()["cached"] is False
        assert len(graph_calls) == 2, "a different user must not get another user's cached answer"
