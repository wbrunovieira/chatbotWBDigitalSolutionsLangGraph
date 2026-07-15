"""
Per-request cost accumulation.

The spend cap is only as good as the number fed into it, so this is the piece that
actually connects "the LLM was called" to "the budget went down".
"""

import asyncio

import pytest

from deepseek_optimizer import (
    DeepSeekOptimizer,
    add_request_cost,
    begin_request_cost,
    get_request_cost,
)


@pytest.fixture(autouse=True)
def fresh_counters():
    DeepSeekOptimizer.token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "api_calls": 0,
        "cached_responses": 0,
    }
    yield


class TestRequestCostAccumulator:
    def test_starts_at_zero(self):
        begin_request_cost()
        assert get_request_cost() == 0.0

    def test_accumulates_multiple_llm_calls(self):
        # One /chat request fans out into up to 3 DeepSeek calls
        # (detect_intent -> generate_response -> revise_response).
        begin_request_cost()
        add_request_cost(0.01)
        add_request_cost(0.02)
        add_request_cost(0.03)
        assert get_request_cost() == pytest.approx(0.06)

    def test_begin_resets_between_requests(self):
        begin_request_cost()
        add_request_cost(0.05)

        begin_request_cost()
        assert get_request_cost() == 0.0

    def test_add_outside_a_request_is_a_no_op(self):
        # Must not raise: background/startup code may call the optimizer with no
        # request context active.
        add_request_cost(0.01)

    async def test_survives_being_written_from_a_child_task(self):
        """
        LangGraph may run nodes in child asyncio tasks, and a child task gets a
        *copy* of the context. A ContextVar holding a plain float would be written
        in the copy and the handler would read back 0.0 — silently disabling the
        spend cap. The accumulator must be a shared mutable, so this must pass.
        """
        begin_request_cost()

        async def node():
            add_request_cost(0.04)

        await asyncio.gather(asyncio.create_task(node()), asyncio.create_task(node()))

        assert get_request_cost() == pytest.approx(0.08)

    async def test_requests_do_not_bleed_cost_into_each_other(self):
        """Concurrent /chat requests must each bill only their own LLM calls."""

        async def one_request(cost: float) -> float:
            begin_request_cost()
            add_request_cost(cost)
            await asyncio.sleep(0)  # force interleaving
            add_request_cost(cost)
            return get_request_cost()

        results = await asyncio.gather(one_request(0.01), one_request(0.10))
        assert results == [pytest.approx(0.02), pytest.approx(0.20)]


class TestUpdateUsageFeedsTheAccumulator:
    def test_api_call_adds_its_cost_to_the_request(self):
        begin_request_cost()
        DeepSeekOptimizer.update_usage(input_tokens=10_000, output_tokens=1_000, cache_hit=False)
        assert get_request_cost() > 0

    def test_cost_matches_the_optimizer_estimate(self):
        begin_request_cost()
        expected, _ = DeepSeekOptimizer.estimate_cost(10_000, 1_000, cache_hit=False)
        DeepSeekOptimizer.update_usage(input_tokens=10_000, output_tokens=1_000, cache_hit=False)
        assert get_request_cost() == pytest.approx(expected)

    def test_locally_cached_responses_cost_nothing(self):
        # A Redis/pattern cache hit never touches DeepSeek, so it must not consume budget.
        begin_request_cost()
        DeepSeekOptimizer.update_usage(is_cached_response=True)
        assert get_request_cost() == 0.0
