"""Behavioral context: scoring, summary, and personalization hint (#8b)."""

import behavior


class TestScoreLead:
    def test_none_or_empty_scores_zero(self):
        assert behavior.score_lead(None) == 0
        assert behavior.score_lead({}) == 0
        assert behavior.score_lead({"pages_visited": []}) == 0

    def test_more_pages_scores_higher(self):
        shallow = behavior.score_lead({"pages_visited": ["/", "/blog"]})
        deep = behavior.score_lead({"pages_visited": ["/", "/blog", "/about", "/websites", "/faq"]})
        assert 0 < shallow < deep

    def test_hot_pages_add_weight(self):
        cold = behavior.score_lead({"pages_visited": ["/", "/blog"]})
        hot = behavior.score_lead({"pages_visited": ["/", "/pricing", "/contact"]})
        assert hot > cold

    def test_explicit_journey_score_fraction_and_absolute(self):
        # a 0–1 fraction and an absolute 0–40 value both contribute, capped at 100
        assert behavior.score_lead({"journey_score": 1.0}) == 40
        assert behavior.score_lead({"journey_score": 40}) == 40
        # deep + all-hot + max journey overflows and clamps to 100
        assert behavior.score_lead({"journey_score": 999, "pages_visited": ["/pricing", "/contact"] * 5}) == 100

    def test_score_is_bounded_0_100(self):
        s = behavior.score_lead({"pages_visited": ["/pricing", "/contact"] * 30, "journey_score": 1.0})
        assert 0 <= s <= 100


class TestSummarize:
    def test_empty_is_blank(self):
        assert behavior.summarize_behavior(None) == ""
        assert behavior.summarize_behavior({}) == ""

    def test_includes_pages_geo_journey(self):
        out = behavior.summarize_behavior(
            {"pages_visited": ["/", "/pricing"], "geo_country": "BR", "journey_score": 0.8}
        )
        assert "visited 2 pages" in out and "/pricing" in out
        assert "country=BR" in out
        assert "journey_score=0.8" in out

    def test_truncates_long_page_lists(self):
        out = behavior.summarize_behavior({"pages_visited": [f"/p{i}" for i in range(12)]})
        assert "visited 12 pages" in out and "+4 more" in out


class TestPersonalizationHint:
    def test_blank_when_no_behavior(self):
        assert behavior.personalization_hint(None) == ""

    def test_forbids_revealing_tracking(self):
        hint = behavior.personalization_hint({"pages_visited": ["/pricing"], "geo_country": "BR"})
        assert hint
        assert "never reveal" in hint.lower()
        assert "/pricing" in hint  # the signal is present for the model


class TestAsDict:
    def test_passes_dict_and_none(self):
        assert behavior.as_dict(None) is None
        assert behavior.as_dict({"a": 1}) == {"a": 1}

    def test_coerces_pydantic_like(self):
        class M:
            def model_dump(self):
                return {"pages_visited": ["/x"]}

        assert behavior.as_dict(M()) == {"pages_visited": ["/x"]}
