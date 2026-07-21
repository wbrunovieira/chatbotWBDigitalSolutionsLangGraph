"""
Shared fixtures.

Every test runs against a fakeredis instance and against a fully stubbed LLM /
vector-store layer: the suite must never reach DeepSeek, Qdrant, Langfuse or the
network, and must never spend a cent.
"""

import os

import pytest
from fakeredis import aioredis as fake_aioredis

# Must be set before `config` is imported, since config reads env at import time.
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("QDRANT_HOST", "http://localhost:6333")
os.environ.setdefault("ADMIN_API_TOKEN", "test-admin-token")

from core import cache  # noqa: E402
import config  # noqa: E402
from rag import db  # noqa: E402


class _UnstubbedQdrant:
    """Any attribute use raises — so a test that reaches Qdrant without stubbing fails loudly."""

    def __getattr__(self, name):
        raise AssertionError(
            f"Qdrant client not stubbed in this test (called .{name}). "
            "Set db.set_qdrant_client(fake) — the suite must never reach a real Qdrant."
        )


@pytest.fixture(autouse=True)
def guard_qdrant_singleton():
    # Nodes fetch the client from db.get_qdrant_client(); default it to a guard so a missing
    # stub errors instead of silently dialing http://localhost:6333. Tests that need Qdrant
    # override this with db.set_qdrant_client(fake).
    db.set_qdrant_client(_UnstubbedQdrant())
    yield
    db.set_qdrant_client(None)


@pytest.fixture
def redis_fake():
    """A clean fakeredis for each test, injected through cache.set_redis()."""
    client = fake_aioredis.FakeRedis(decode_responses=False)
    cache.set_redis(client)
    yield client
    cache.set_redis(None)


@pytest.fixture
def limits(monkeypatch):
    """
    Small, predictable limits so tests don't have to send 100 requests to trip an
    hourly cap. Returns the values it applied.
    """
    values = {
        "RATE_LIMIT_ENABLED": True,
        "RATE_LIMIT_PER_MINUTE": 3,
        "RATE_LIMIT_PER_HOUR": 5,
        "DAILY_SPEND_LIMIT_USD": 1.0,
        "DAILY_SPEND_LIMIT_PER_IP_USD": 0.10,
        "SPEND_ALERT_THRESHOLD": 0.70,
        # Deliberately not the production default (1000), so the length tests prove
        # the validator reads config at runtime rather than baking the cap in at
        # class-definition time.
        "MAX_MESSAGE_LENGTH": 50,
        # Pin the admin token so /usage-report auth tests are deterministic
        # regardless of any ADMIN_API_TOKEN in the CI environment (setdefault in
        # this file does NOT override an env value already set by the workflow).
        "ADMIN_API_TOKEN": "test-admin-token",
    }
    for key, value in values.items():
        monkeypatch.setattr(config, key, value)
    return values
