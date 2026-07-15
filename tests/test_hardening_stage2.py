"""
Stage 2 hardening: kill the fake streaming endpoint, gate /usage-report behind an
admin token, and disable the interactive docs in production.
"""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import config
import main

ADMIN_TOKEN = "test-admin-token"  # matches conftest's os.environ default


@pytest_asyncio.fixture
async def raw_client(redis_fake, limits):
    """Client over the real app, no graph stubbing — enough for /usage-report, docs, stream."""
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class TestChatStreamRemoved:
    async def test_chat_stream_is_gone(self, raw_client):
        # It was a fake endpoint returning hardcoded strings; the widget uses /chat.
        resp = await raw_client.post("/chat/stream", json={"message": "oi"})
        assert resp.status_code in (404, 405)


class TestUsageReportAuth:
    async def test_no_token_is_rejected(self, raw_client):
        assert (await raw_client.get("/usage-report")).status_code == 401

    async def test_wrong_token_is_rejected(self, raw_client):
        resp = await raw_client.get(
            "/usage-report", headers={"Authorization": "Bearer nope"}
        )
        assert resp.status_code == 401

    async def test_correct_token_is_accepted(self, raw_client):
        resp = await raw_client.get(
            "/usage-report", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    async def test_report_includes_spend_snapshot(self, raw_client):
        resp = await raw_client.get(
            "/usage-report", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        body = resp.json()
        assert "spend" in body
        assert body["spend"]["daily_limit_usd"] == config.DAILY_SPEND_LIMIT_USD

    async def test_deny_when_no_admin_token_configured(self, raw_client, monkeypatch):
        # A misconfigured deploy (no token) must fail closed, not open the endpoint.
        monkeypatch.setattr(config, "ADMIN_API_TOKEN", None)
        resp = await raw_client.get(
            "/usage-report", headers={"Authorization": "Bearer anything"}
        )
        assert resp.status_code == 401


class TestDocsKwargs:
    def test_production_disables_all_doc_routes(self):
        kwargs = main.docs_kwargs(is_production=True)
        assert kwargs == {"docs_url": None, "redoc_url": None, "openapi_url": None}

    def test_non_production_keeps_framework_defaults(self):
        assert main.docs_kwargs(is_production=False) == {}

    async def test_production_app_returns_404_for_docs(self):
        # Prove the kwargs actually disable the routes, without rebuilding the whole app.
        probe = FastAPI(**main.docs_kwargs(is_production=True))
        transport = ASGITransport(app=probe)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            for path in ("/docs", "/redoc", "/openapi.json"):
                assert (await c.get(path)).status_code == 404

    async def test_dev_app_serves_openapi(self, raw_client):
        # In the test env (APP_ENV unset => not production) docs must stay on.
        assert (await raw_client.get("/openapi.json")).status_code == 200


class TestCorsConfig:
    def test_credentials_disabled_and_write_verbs_dropped(self):
        # allow_credentials was pointless (no cookies) and PUT/DELETE are unused.
        cors = _cors_options(main.app)
        assert cors["allow_credentials"] is False
        assert set(cors["allow_methods"]) == {"GET", "POST", "OPTIONS"}

    def test_allowlist_still_has_the_site(self):
        cors = _cors_options(main.app)
        assert "https://www.wbdigitalsolutions.com" in cors["allow_origins"]


def _cors_options(app) -> dict:
    from starlette.middleware.cors import CORSMiddleware

    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            return mw.kwargs
    raise AssertionError("CORSMiddleware not installed")
