"""needs_revision gating: revision stays off the hot path (#2)."""

import config
from nodes.revision import needs_revision


class TestNeedsRevision:
    def test_short_answer_is_not_revised(self):
        # The common case: a short, direct reply skips the second LLM call.
        assert needs_revision({"response": "Depende do escopo. Fale com a gente!"}) is False

    def test_long_answer_is_revised(self):
        assert needs_revision({"response": "x" * (config.REVISION_MAX_LENGTH + 1)}) is True

    def test_at_threshold_is_not_revised(self):
        assert needs_revision({"response": "x" * config.REVISION_MAX_LENGTH}) is False

    def test_tool_driven_reply_is_never_revised(self):
        # A curated tool reply (booking link, lead confirmation) must not be rewritten,
        # even when it's long.
        state = {"response": "y" * (config.REVISION_MAX_LENGTH + 100), "tool_results": [{"ok": 1}]}
        assert needs_revision(state) is False

    def test_missing_response_is_not_revised(self):
        assert needs_revision({}) is False
