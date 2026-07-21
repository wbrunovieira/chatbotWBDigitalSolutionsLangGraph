"""Rate limiting, spend cap and client-IP resolution."""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import config
from safety import security


def make_request(headers: dict | None = None, peer: str = "10.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 12345)})


class TestGetClientIp:
    def test_prefers_cloudflare_header_over_nginx(self):
        # Once behind the Cloudflare proxy, X-Real-IP becomes the edge IP, so
        # CF-Connecting-IP has to win or every visitor collapses into a few buckets.
        request = make_request({"cf-connecting-ip": "203.0.113.7", "x-real-ip": "172.16.0.9"})
        assert security.get_client_ip(request) == "203.0.113.7"

    def test_falls_back_to_x_real_ip(self):
        request = make_request({"x-real-ip": "203.0.113.8"})
        assert security.get_client_ip(request) == "203.0.113.8"

    def test_takes_first_entry_of_x_forwarded_for(self):
        request = make_request({"x-forwarded-for": "203.0.113.9, 172.16.0.1"})
        assert security.get_client_ip(request) == "203.0.113.9"

    def test_falls_back_to_socket_peer_when_no_headers(self):
        assert security.get_client_ip(make_request(peer="198.51.100.4")) == "198.51.100.4"


class TestRateLimit:
    async def test_allows_requests_up_to_the_minute_limit(self, redis_fake, limits):
        for _ in range(limits["RATE_LIMIT_PER_MINUTE"]):
            await security.check_rate_limit("1.2.3.4")

    async def test_blocks_with_429_past_the_minute_limit(self, redis_fake, limits):
        for _ in range(limits["RATE_LIMIT_PER_MINUTE"]):
            await security.check_rate_limit("1.2.3.4")

        with pytest.raises(HTTPException) as exc:
            await security.check_rate_limit("1.2.3.4")

        assert exc.value.status_code == 429
        assert exc.value.headers["Retry-After"] == "60"

    async def test_limits_are_per_ip(self, redis_fake, limits):
        for _ in range(limits["RATE_LIMIT_PER_MINUTE"]):
            await security.check_rate_limit("1.2.3.4")

        # A different IP must not inherit the first one's budget.
        await security.check_rate_limit("5.6.7.8")

    async def test_hourly_limit_trips_with_its_own_retry_after(self, redis_fake, limits, monkeypatch):
        # Lift the per-minute cap so the hourly one is what actually trips.
        monkeypatch.setattr(config, "RATE_LIMIT_PER_MINUTE", 10_000)

        for _ in range(limits["RATE_LIMIT_PER_HOUR"]):
            await security.check_rate_limit("1.2.3.4")

        with pytest.raises(HTTPException) as exc:
            await security.check_rate_limit("1.2.3.4")

        assert exc.value.status_code == 429
        assert exc.value.headers["Retry-After"] == "3600"

    async def test_can_be_disabled_by_config(self, redis_fake, limits, monkeypatch):
        monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
        for _ in range(limits["RATE_LIMIT_PER_MINUTE"] * 5):
            await security.check_rate_limit("1.2.3.4")


class TestSpendCap:
    async def test_allows_calls_while_under_budget(self, redis_fake, limits):
        await security.record_spend("1.2.3.4", 0.01)
        await security.check_spend_cap("1.2.3.4")

    async def test_opens_the_circuit_with_503_at_the_global_cap(self, redis_fake, limits):
        await security.record_spend("1.2.3.4", limits["DAILY_SPEND_LIMIT_USD"])

        # A *different* IP is blocked too: the global cap protects the invoice, not the IP.
        with pytest.raises(HTTPException) as exc:
            await security.check_spend_cap("9.9.9.9")

        assert exc.value.status_code == 503

    async def test_per_ip_cap_blocks_the_abuser_only(self, redis_fake, limits):
        await security.record_spend("1.2.3.4", limits["DAILY_SPEND_LIMIT_PER_IP_USD"])

        with pytest.raises(HTTPException) as exc:
            await security.check_spend_cap("1.2.3.4")
        assert exc.value.status_code == 503

        # Everyone else keeps working — one abuser must not take the bot offline.
        await security.check_spend_cap("5.6.7.8")

    async def test_spend_accumulates_across_requests(self, redis_fake, limits):
        for _ in range(4):
            await security.record_spend("1.2.3.4", 0.02)

        snapshot = await security.get_spend_snapshot()
        assert snapshot["spent_usd"] == pytest.approx(0.08)

    async def test_zero_cost_requests_do_not_touch_the_counters(self, redis_fake, limits):
        await security.record_spend("1.2.3.4", 0.0)
        snapshot = await security.get_spend_snapshot()
        assert snapshot["spent_usd"] == 0.0

    async def test_alert_fires_once_when_crossing_the_threshold(self, redis_fake, limits, caplog):
        # 70% of a $1.00 cap.
        with caplog.at_level("ERROR"):
            await security.record_spend("1.2.3.4", 0.60)
            assert "SPEND ALERT" not in caplog.text

            await security.record_spend("1.2.3.4", 0.15)  # now at $0.75 = 75%
            assert "SPEND ALERT" in caplog.text

            caplog.clear()
            await security.record_spend("1.2.3.4", 0.05)  # still over threshold
            assert "SPEND ALERT" not in caplog.text  # but must not alert twice a day

    async def test_snapshot_reports_circuit_state(self, redis_fake, limits):
        assert (await security.get_spend_snapshot())["circuit_open"] is False

        await security.record_spend("1.2.3.4", limits["DAILY_SPEND_LIMIT_USD"])
        snapshot = await security.get_spend_snapshot()

        assert snapshot["circuit_open"] is True
        assert snapshot["percent_used"] >= 100.0


class TestEnforceChatLimits:
    async def test_returns_the_client_ip(self, redis_fake, limits):
        request = make_request({"x-real-ip": "203.0.113.5"})
        assert await security.enforce_chat_limits(request) == "203.0.113.5"

    async def test_propagates_the_429(self, redis_fake, limits):
        request = make_request({"x-real-ip": "203.0.113.5"})
        for _ in range(limits["RATE_LIMIT_PER_MINUTE"]):
            await security.enforce_chat_limits(request)

        with pytest.raises(HTTPException) as exc:
            await security.enforce_chat_limits(request)
        assert exc.value.status_code == 429

    async def test_fails_open_when_redis_is_down(self, limits, monkeypatch, caplog):
        class DeadRedis:
            def pipeline(self):
                raise ConnectionError("redis is down")

            async def get(self, *a, **kw):
                raise ConnectionError("redis is down")

        monkeypatch.setattr("safety.security.get_redis", lambda: DeadRedis())
        request = make_request({"x-real-ip": "203.0.113.5"})

        with caplog.at_level("ERROR"):
            # Deliberate trade-off: a Redis outage must not take the chatbot down.
            assert await security.enforce_chat_limits(request) == "203.0.113.5"

        assert "FAILING OPEN" in caplog.text
