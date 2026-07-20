"""Semantic cache (#12): cosine + bounded per-bucket get/put over Redis."""

import pytest

import cache


class TestCosine:
    def test_identical_vectors_are_one(self):
        assert cache._cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal_is_zero(self):
        assert cache._cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_degenerate_inputs_are_zero(self):
        assert cache._cosine([], [1.0]) == 0.0
        assert cache._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
        assert cache._cosine([1.0, 2.0], [1.0]) == 0.0  # length mismatch


class TestSemanticGetPut:
    async def test_hit_above_threshold(self, redis_fake):
        await cache.semantic_put("b1", [1.0, 0.0], {"answer": "sites!"}, max_entries=10)
        # a near-identical vector clears the threshold
        hit = await cache.semantic_get("b1", [0.99, 0.01], threshold=0.92)
        assert hit == {"answer": "sites!"}

    async def test_miss_below_threshold(self, redis_fake):
        await cache.semantic_put("b1", [1.0, 0.0], {"answer": "sites!"}, max_entries=10)
        assert await cache.semantic_get("b1", [0.0, 1.0], threshold=0.92) is None

    async def test_empty_bucket_is_none(self, redis_fake):
        assert await cache.semantic_get("nope", [1.0, 0.0], threshold=0.5) is None

    async def test_picks_the_most_similar_entry(self, redis_fake):
        await cache.semantic_put("b1", [1.0, 0.0], {"a": 1}, max_entries=10)
        await cache.semantic_put("b1", [0.0, 1.0], {"a": 2}, max_entries=10)
        hit = await cache.semantic_get("b1", [0.1, 0.99], threshold=0.5)
        assert hit == {"a": 2}

    async def test_bucket_is_bounded(self, redis_fake):
        import json
        for i in range(10):
            await cache.semantic_put("b1", [float(i), 1.0], {"i": i}, max_entries=3)
        entries = json.loads(await redis_fake.get("b1"))
        assert len(entries) == 3
        assert [e["payload"]["i"] for e in entries] == [7, 8, 9]  # most recent kept
